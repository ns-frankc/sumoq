import asyncio
import base64
import os
import re
import shutil
from enum import Enum

import aiohttp
import asyncclick
import pyperclip
import yaml
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion, FuzzyCompleter
from prompt_toolkit.patch_stdout import patch_stdout
from pupdb.core import PupDB

_cwd = os.path.abspath(os.path.dirname(__file__))
_encode = "utf-8"
_sumo_api_base = "https://api.sumologic.com/api/v1"
_default_conf_name = "default-conf.yml"
_toolbar_fields = ""
_toolbar_ns = ""
_toolbar_idx = ""
_db = PupDB(os.path.join(_cwd, "db.json"))


class CompletionMode(Enum):
    FIELD = 1
    VALUE = 2
    WHERE_VALUE = 3


class SumoQueryCompleter(Completer):
    _re_field_unit = r"([\w\.]+|%\".+\")"
    _re_value_unit = r"([\w\-:/\.+@#\$%\^]+|\".*\")"
    _re_not = r"((?i:not)\s+)"
    _re_and_or_not = r"((?i:(and|or))(\s+(?i:not)\s+\(|\s+)+)"
    _re_fields = (
        rf"^({_re_not}?"
        rf"\(*{_re_field_unit}={_re_value_unit}\)*\s+"
        rf"{_re_and_or_not}*)*"
    )
    _re_sumo_op = r"(.|\s)*\|\s*$"
    _re_where_fields = (
        rf"(.|\s)*\|\s*where\s+{_re_not}?"
        rf"\(*({_re_field_unit}={_re_value_unit}\)*\s+"
        rf"{_re_and_or_not}+)*"
    )
    RULES = (
        (_re_fields + r"$", "field"),
        (_re_fields + r"_index=$", "index"),
        (_re_fields + r"_sourceName=$", "src_name"),
        (_re_fields + r"_loglevel=$", "log_level"),
        (_re_sumo_op, "sumo_op"),
        (_re_where_fields + r"$", "where_field"),
        (
            _re_where_fields + r"(?P<where_field>([\w\.]+|%\".+\"))=$",
            "where_value",
        ),
    )
    COMPILED_RULES = [(re.compile(r[0]), r[1]) for r in RULES]
    FIELD_SPECIAL_CHAR_CHECK = re.compile(r"(^[\d\.]|.*[\W\.]|.*\.\.)")
    VALUE_SPECIAL_CHAR_CHECK = re.compile(r"[^\w\-:/\.+@#\$%\^]")

    LOG_LEVELS = ("trace", "debug", "info", "warn", "error", "critical")
    BUILT_IN_FIELDS = [
        "_collector",
        "_messageCount",
        "_messageTime",
        "_raw",
        "_receiptTime",
        "_size",
        "_source",
        "_sourceCategory",
        "_sourceHost",
        "_sourceName",
        "_format",
        "_view",
        "_index",
    ]
    SUMO_OPS = (
        "parse",
        "format",
        "formatDate",
        "json",
        "where",
        "count",
        "sort by",
        "json",
        "count",
        "count_distinct",
        "count_frequent",
        "min",
        "max",
        "sum",
        "values",
    )

    def get_completions(self, document, complete_ev):
        global _db

        cur_text = document.text_before_cursor
        for r, name in self.COMPILED_RULES:
            if matched := re.match(r, cur_text):
                if name == "index":
                    yield from self._yeild_completions(
                        _db.get(DBKeys.INDEXES) or []
                    )
                elif name == "src_name":
                    yield from self._yeild_completions(
                        _db.get(DBKeys.NAMESPACES) or []
                    )
                elif name == "log_level":
                    yield from self._yeild_completions(self.LOG_LEVELS)
                elif name == "field":
                    yield from self._yeild_completions(
                        self.BUILT_IN_FIELDS + _db.get(DBKeys.FIELDS) or [],
                        mode=CompletionMode.FIELD,
                    )
                elif name == "sumo_op":
                    yield from self._yeild_completions(self.SUMO_OPS)
                elif name == "where_field":
                    yield from self._yeild_completions(
                        (_db.get(DBKeys.JSON_APP) or {}).keys(),
                        mode=CompletionMode.FIELD,
                    )
                elif name == "where_value":
                    field = matched.group("where_field")
                    if field.startswith('%"'):
                        field = field.lstrip('%"').rstrip('"')
                    yield from self._yeild_completions(
                        (_db.get(DBKeys.JSON_APP) or {}).get(field) or [],
                        mode=CompletionMode.WHERE_VALUE,
                    )
                break

    def _yeild_completions(self, values, mode=CompletionMode.VALUE):
        for v in values:
            if mode is CompletionMode.FIELD:
                if re.match(self.FIELD_SPECIAL_CHAR_CHECK, v):
                    v = f'%"{v}"'
                v += "="
            elif mode is CompletionMode.VALUE:
                if re.match(self.VALUE_SPECIAL_CHAR_CHECK, v):
                    v = f'"{v}"'
            elif mode is CompletionMode.WHERE_VALUE:
                if isinstance(v, str):
                    v = f'"{v}"'
                elif isinstance(v, bool):
                    v = f'"{v}"'.lower()

            yield Completion(v)


class DBKeys:
    NAMESPACES = "namespaces"
    FIELDS = "fields"
    INDEXES = "idx"
    JSON_APP = "json_app"


def read_keys(keys):
    if not keys:
        raise ValueError()

    with open(keys, "r") as kfp:
        kconf = yaml.load(kfp, Loader=yaml.loader.SafeLoader)
    return kconf["accessID"], kconf["accessKey"]


def read_conf_fields_idx(conf):
    global _db, _toolbar_idx, _toolbar_fields
    with open(conf, "r") as cfp:
        conf = yaml.load(cfp, Loader=yaml.loader.SafeLoader)

    _db.set(DBKeys.FIELDS, conf.get("custom_fields") or [])
    _db.set(DBKeys.INDEXES, conf.get("indexes") or [])
    _toolbar_fields = "using conf"
    _toolbar_idx = "using conf"


def get_toolbar():
    global _toolbar_fields, _toolbar_ns, _toolbar_idx
    return (
        "<tab> select a completion. <esc> <enter> to exit. "
        "fields: {:<15} namespaces: {:<15} indexes: {:<15}"
    ).format(_toolbar_fields, _toolbar_ns, _toolbar_idx)


@asyncclick.command()
@asyncclick.option("-c", "--conf", help="config file path")
@asyncclick.option("-k", "--keys", help="Sumo Logic API key file path")
@asyncclick.option("-kc", "--kubeconf", help="kubectl config file path")
@asyncclick.option("-cd", "--clean-db", is_flag=True, help="clean up db first")
@asyncclick.option(
    "-g",
    "--generate-conf",
    type=asyncclick.Path(),
    help="Generate a config file from the default config",
)
async def cli(conf, keys, kubeconf, clean_db, generate_conf):
    global _default_conf_name, _toolbar_fields, _toolbar_idx

    if generate_conf:
        shutil.copy(
            os.path.join(_cwd, _default_conf_name),
            os.path.abspath(os.path.expanduser(generate_conf)),
        )
        return
    if clean_db:
        _db.truncate_db()

    conf = conf or os.path.join(_cwd, _default_conf_name)
    session = None
    if auth_header := get_auth_header(keys):
        session = aiohttp.ClientSession(headers={"Authorization": auth_header})
        asyncio.create_task(fetch_custom_fields(session))
        asyncio.create_task(fetch_idx(session))
    elif _db.get(DBKeys.INDEXES):
        _toolbar_fields = "using cache"
        _toolbar_idx = "using cache"
    else:
        read_conf_fields_idx(conf)
    asyncio.create_task(fetch_namespaces(kubeconf))
    asyncio.create_task(fetch_json_suggestions(conf))

    try:
        p_session = PromptSession()
        with patch_stdout():
            result = await p_session.prompt_async(
                "query> ",
                multiline=True,
                completer=FuzzyCompleter(SumoQueryCompleter()),
                auto_suggest=AutoSuggestFromHistory(),
                bottom_toolbar=get_toolbar,
                refresh_interval=1.0,
            )

        pyperclip.copy(result)
        asyncclick.echo("\nCopied to clipboard")
    finally:
        try:
            await session.close()
        except AttributeError:
            pass


def get_auth_header(keys):
    global _encode
    if not keys:
        return
    aid, ak = read_keys(keys)

    header_token = base64.b64encode(f"{aid}:{ak}".encode(_encode))
    header_token = header_token.decode(_encode)
    return f"Basic {header_token}"


async def fetch_idx(session):
    global _db, _sumo_api_base, _toolbar_idx

    _toolbar_idx = "loading"
    cursor = None
    params = {"limit": 1000}
    idx = []

    while True:
        async with session.get(
            f"{_sumo_api_base}/partitions",
            params=params,
        ) as resp:
            resp_dict = await resp.json()

        idx.extend(d["name"] for d in resp_dict.get("data") or [])

        if not (cursor := resp_dict.get("next")):
            break
        else:
            params["token"] = cursor

    _db.set(DBKeys.INDEXES, idx)
    _toolbar_idx = "loaded"


async def fetch_custom_fields(session):
    global _db, _sumo_api_base, _toolbar_fields

    _toolbar_fields = "loading"
    async with session.get(
        f"{_sumo_api_base}/fields",
    ) as resp:
        resp_dict = await resp.json()

    _db.set(
        DBKeys.FIELDS, [d["fieldName"] for d in resp_dict.get("data") or []]
    )
    _toolbar_fields = "loaded"


async def fetch_namespaces(kubeconf):
    """Fetch all possible namespaces from k8s.

    Uses kubectl for now, ideally we can change to use an async k8s client in
    the future.
    """
    global _db, _encode, _toolbar_ns
    if not kubeconf:
        _toolbar_ns = "using cache"
        return

    _toolbar_ns = "loading"
    conf_path = os.path.abspath(os.path.expanduser(kubeconf))

    proc = await asyncio.create_subprocess_shell(
        f"kubectl --kubeconfig {conf_path} get namespaces",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()
    if proc.returncode != 0 or stderr:
        return

    _db.set(
        DBKeys.NAMESPACES,
        [
            line.split(" ", 1)[0]
            for line in stdout.decode(_encode).split("\n")[1:]
        ],
    )
    _toolbar_ns = "loaded"


async def fetch_json_suggestions(conf):
    global _db
    with open(conf, "r") as cfp:
        conf_dict = yaml.load(cfp, Loader=yaml.SafeLoader)

    _db.set(DBKeys.JSON_APP, conf_dict.get("app_json") or {})


if __name__ == "__main__":
    asyncio.run(cli())
