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


class SumoQueryCompleter(Completer):
    _re_fields = r"^(\w+=[\w\"]+\s*)*"
    RULES = (
        (_re_fields + r"_index=$", "index"),
        (_re_fields + r"_sourceName=$", "src_name"),
        (_re_fields + r"_loglevel=$", "log_level"),
    )
    COMPILED_RULES = [(re.compile(r[0]), r[1]) for r in RULES]

    LOG_LEVELS = ("trace", "debug", "info", "warn", "error", "critical")

    def get_completions(self, document, complete_ev):
        global _indexes

        cur_text = document.text_before_cursor
        for r, name in self.COMPILED_RULES:
            if _ := re.match(r, cur_text):
                if name == "index":
                    for idx in _indexes:
                        yield Completion(idx)
                elif name == "src_name":
                    # namespaces
                    pass
                elif name == "log_level":
                    for lvl in self.LOG_LEVELS:
                        yield Completion(lvl)


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

    asyncio.create_task(fetch_idx(keys, conf))

    p_session = PromptSession()
    with patch_stdout():
        result = await p_session.prompt_async(
            "Query:",
            multiline=True,
            completer=FuzzyCompleter(SumoQueryCompleter()),
        )
    print(result)


async def fetch_idx(keys, conf):
    global _indexes, _encode

    try:
        aid, ak = read_keys(keys)
    except ValueError:
        _indexes.extend(read_conf_idx(conf))
        return

    cursor = None
    params = {"limit": 1000}
    header_token = base64.b64encode(f"{aid}:{ak}".encode(_encode))
    header_token = header_token.decode(_encode)

    async with aiohttp.ClientSession() as session:
        while True:
            if cursor:
                params["token"] = cursor
            else:
                params.pop("token", None)

            async with session.get(
                "https://api.sumologic.com/api/v1/partitions",
                params=params,
                headers={"Authorization": f"Basic {header_token}"},
            ) as resp:
                resp_dict = await resp.json()

                for d in resp_dict.get("data") or []:
                    _indexes.append(d["name"])

                if not (cursor := resp_dict.get("next")):
                    break


if __name__ == "__main__":
    asyncio.run(cli())
