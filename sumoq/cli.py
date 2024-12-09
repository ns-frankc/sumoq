import asyncio
import base64
import os
import re
from enum import Enum

import aiohttp
import asyncclick
import pyperclip
import yaml
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion, FuzzyCompleter
from prompt_toolkit.patch_stdout import patch_stdout

_indexes = []
_cwd = os.path.abspath(os.path.dirname(__file__))
_encode = "utf-8"
_custom_fields = []
_namespaces = []
_json_suggestions = {}
_sumo_api_base = "https://api.sumologic.com/api/v1"


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
        global _indexes, _custom_fields, _namespaces

        cur_text = document.text_before_cursor
        for r, name in self.COMPILED_RULES:
            if matched := re.match(r, cur_text):
                if name == "index":
                    yield from self._yeild_completions(_indexes)
                elif name == "src_name":
                    yield from self._yeild_completions(_namespaces)
                elif name == "log_level":
                    yield from self._yeild_completions(self.LOG_LEVELS)
                elif name == "field":
                    yield from self._yeild_completions(
                        self.BUILT_IN_FIELDS + _custom_fields,
                        mode=CompletionMode.FIELD,
                    )
                elif name == "sumo_op":
                    yield from self._yeild_completions(self.SUMO_OPS)
                elif name == "where_field":
                    yield from self._yeild_completions(
                        _json_suggestions.keys(), mode=CompletionMode.FIELD
                    )
                elif name == "where_value":
                    field = matched.group("where_field")
                    if field.startswith('%"'):
                        field = field.lstrip('%"').rstrip('"')
                    yield from self._yeild_completions(
                        _json_suggestions.get(field) or [],
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


def read_keys(keys):
    if not keys:
        raise ValueError()

    with open(keys, "r") as kfp:
        kconf = yaml.load(kfp, Loader=yaml.loader.SafeLoader)
    return kconf["accessID"], kconf["accessKey"]


def read_conf_idx(conf):
    if not conf:
        return []

    with open(conf, "r") as cfp:
        conf = yaml.load(cfp, Loader=yaml.loader.SafeLoader)

    return conf.get("indexes") or []


@asyncclick.command()
@asyncclick.option("-c", "--conf", help="config file path")
@asyncclick.option("-k", "--keys", help="Sumo Logic API key file path")
@asyncclick.option("-kc", "--kubeconf", help="kubectl config file path")
async def cli(conf, keys, kubeconf):
    global _indexes

    headers = {"Authorization": get_auth_header(keys, conf)}
    session = aiohttp.ClientSession(headers=headers)
    asyncio.create_task(fetch_custom_fields(session))
    asyncio.create_task(fetch_idx(session))
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
                bottom_toolbar=(
                    "<tab> select a completion. <esc> <enter> to exit."
                ),
            )
        asyncclick.echo(result)

        pyperclip.copy(result)
        asyncclick.echo("\nCopied to clipboard")
    finally:
        await session.close()


def get_auth_header(keys, conf):
    global _encode

    try:
        aid, ak = read_keys(keys)
    except ValueError:
        _indexes.extend(read_conf_idx(conf))
        return

    header_token = base64.b64encode(f"{aid}:{ak}".encode(_encode))
    header_token = header_token.decode(_encode)
    return f"Basic {header_token}"


async def fetch_idx(session):
    global _indexes, _sumo_api_base

    cursor = None
    params = {"limit": 1000}

    while True:
        if cursor:
            params["token"] = cursor
        else:
            params.pop("token", None)

        async with session.get(
            f"{_sumo_api_base}/partitions",
            params=params,
        ) as resp:
            resp_dict = await resp.json()

        _indexes.extend(d["name"] for d in resp_dict.get("data") or [])

        if not (cursor := resp_dict.get("next")):
            break


async def fetch_custom_fields(session):
    global _custom_fields, _sumo_api_base

    async with session.get(
        f"{_sumo_api_base}/fields",
    ) as resp:
        resp_dict = await resp.json()

    _custom_fields.extend(d["fieldName"] for d in resp_dict.get("data") or [])


async def fetch_namespaces(kubeconf):
    """Fetch all possible namespaces from k8s.

    Uses kubectl for now, ideally we can change to use an async k8s client in
    the future.
    """
    if not kubeconf:
        return

    global _namespaces, _encode
    conf_path = os.path.abspath(os.path.expanduser(kubeconf))

    proc = await asyncio.create_subprocess_shell(
        f"kubectl --kubeconfig {conf_path} get namespaces",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()
    if proc.returncode != 0 or stderr:
        return

    _namespaces.extend(
        line.split(" ", 1)[0]
        for line in stdout.decode(_encode).split("\n")[1:]
    )


async def fetch_json_suggestions(conf):
    global _cwd, _json_suggestions

    if not conf:
        conf = os.path.join(_cwd, "default-config.yml")

    with open(conf, "r") as cfp:
        conf_dict = yaml.load(cfp, Loader=yaml.SafeLoader)

    _json_suggestions = conf_dict.get("app_json") or {}


if __name__ == "__main__":
    asyncio.run(cli())
