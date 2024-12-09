import asyncio
import base64
import os
import re

import aiohttp
import asyncclick
import yaml
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, FuzzyCompleter
from prompt_toolkit.patch_stdout import patch_stdout

_indexes = []
_cwd = os.path.abspath(__file__)
_encode = "utf-8"
_custom_fields = []
_sumo_api_base = "https://api.sumologic.com/api/v1"


class SumoQueryCompleter(Completer):
    _re_fields = r"^(\w+=[\w\"]+\s+)*"
    RULES = (
        (_re_fields + r"_index=$", "index"),
        (_re_fields + r"_sourceName=$", "src_name"),
        (_re_fields + r"_loglevel=$", "log_level"),
        (_re_fields, "field"),
    )
    COMPILED_RULES = [(re.compile(r[0]), r[1]) for r in RULES]

    LOG_LEVELS = ("trace", "debug", "info", "warn", "error", "critical")
    BUILT_IN_FIELDS = [
        "_collector=",
        "_messageCount=",
        "_messageTime=",
        "_raw=",
        "_receiptTime=",
        "_size=",
        "_source=",
        "_sourceCategory=",
        "_sourceHost=",
        "_sourceName=",
        "_format=",
        "_view=",
        "_index=",
    ]

    def get_completions(self, document, complete_ev):
        global _indexes, _custom_fields

        cur_text = document.text_before_cursor
        for r, name in self.COMPILED_RULES:
            if _ := re.match(r, cur_text):
                if name == "index":
                    yield from self._yeild_completions(_indexes)
                elif name == "src_name":
                    # namespaces
                    pass
                elif name == "log_level":
                    yield from self._yeild_completions(self.LOG_LEVELS)
                elif name == "field":
                    # This should be checked later than the field values.
                    yield from self._yeild_completions(
                        self.BUILT_IN_FIELDS + _custom_fields
                    )

    def _yeild_completions(self, values):
        for v in values:
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
@asyncclick.option("--conf", help="config file path")
@asyncclick.option("--keys", help="Sumo Logic API key file path")
@asyncclick.option("--kubeconf", help="kubectl config file path")
async def cli(conf, keys, kubeconf):
    global _indexes

    headers = {"Authorization": get_auth_header(keys, conf)}
    session = aiohttp.ClientSession(headers=headers)
    asyncio.create_task(fetch_custom_fields(session))
    asyncio.create_task(fetch_idx(session))

    try:
        p_session = PromptSession()
        with patch_stdout():
            result = await p_session.prompt_async(
                "Query:",
                multiline=True,
                completer=FuzzyCompleter(SumoQueryCompleter()),
            )
        print(result)
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

    _custom_fields.extend(
        f"{d['fieldName']}=" for d in resp_dict.get("data") or []
    )


if __name__ == "__main__":
    asyncio.run(cli())
