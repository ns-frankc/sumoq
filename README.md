This was a project for 2024 Netskope Hackathon.

SumoQ
====

An interactive Sumo Logic Query builder for debug and monitor usage.

Demo
====

https://github.com/user-attachments/assets/1647ba19-ecd3-45a5-a261-158384ed0da7

Installation
====

Since this project is not yet ready to package and upload, installation will
be performed by git clone and running `pip install .`, or `make install` for editable mode.

```sh
git clone https://github.com/ns-frankc/sumoq.git
pushd sumoq
pip install .
```

Get a pair of Sumo Logic API access ID and access key if possible for retrieving completion suggestions. Store them into a local YAML file, e.g. `.access_keys.yml`.
- [Instructions on Sumo Logic doc](https://help.sumologic.com/docs/manage/security/access-keys/#prerequisites)

```yaml
accessID: <access ID>
accessKey: <access key>
```

Get the k8s config YAML from Ranch for retrieving the namespace list. E.g. `~/.kube/config/stork-qa01-mp-npe-iad0-nc1.yaml`.

Quick start
====

<pre><code>
$> sumoq --help
Usage: sumoq [OPTIONS]

Options:
  -c, --conf TEXT           config file path
  -k, --keys TEXT           Sumo Logic API key file path
  -kc, --kubeconf TEXT      k8s config file path
  -cd, --clean-db           clean up db first
  -g, --generate-conf PATH  Generate a config file from the default config
  --help                    Show this message and exit.

$> sumoq -k .access_keys.yml -kc ~/.kube/config/stork-qa01-mp-npe-iad0-nc1.yaml
query>
</code></pre>

- Start typing and the suggestions will appear.
- \<tab\> to rotate through suggestions.
- Current available suggestions
  * Search field names, including builtin and custom fields.
  * `_index` values.
  * `_sourceName` namespaces.
  * Self defined keys and values after `where`.
- \<esc\> \<enter> to complete. The result will be copied to clipboard.

<pre><code>
query> _index=qa01_mp_npe_debug _sourceName=px-1072-box-1656699
       | where %"app-name"="hiveworker" and %"trace.sampled"="true"


Copied to clipboard
</code></pre>

Problem statement
====

The current Sumo Logic log search UI provides only prefix based auto complete. Which is less than useful.

For example, if I want to search a log from "SV5", typing SV5 after `_index=` doesn't give me the `us_sv5_debug` suggestion I want. I would only get `sv5_apiconnector_notify`, which is far from my intention.

<img width="730" alt="image-20241204-031331" src="https://github.com/user-attachments/assets/47fbf89d-50bd-4399-8785-0f3becf0f1c3">

Solution
====

SumoQ provides fuzzy matched suggestions, so engineers wouldn't need to look up into wiki pages and know that SV5's index starts with "us_". As long as "sv5" is typed, "us_sv5_debug" would show up in suggestions.

<img width="1920" alt="image" src="https://github.com/user-attachments/assets/fa46c1d5-7ebd-4e53-803f-e02ae9cd0f68">

This would be especially helpful for seldomly used environments like ruh2 or lon3.

In addition to index, completions for `_sourceName` namespace values are also provided. So engineers don't need to look up the values from k8s.

Cached values
====

The first time API key and k8s config were provided, suggestion values would be stored in a local DB file. Cached values will be used if next time the `-k` and `-kc` options are omitted.

Start with `-cd` option to clean up the db values.

Config file
====

Some suggestions are provided by the config file. If `-c` option was not provided, a default config will be used.

Start with `-g` to generate a config file, and update it for later usage.

```shell
$> sumoq -g config.yml
```

Config file structure
----

```yaml
app_json:
  <filed_name>:
    - <value>
    
indexes:
  - <idx_value>
  
custom_fields:
  - <field_value>
  
namespaces:
  - <ns_value>
```

### app_json

Under this section are the fields and values suggestions after `where`. In our use cases, it represents a parsed json structure. With a parsed JSON log example:

```json
{
    "app-name": "hiveworker",
    "who": "workers",
    "operation-source": "activitychange",
    "operation-type": "ChangeEvent",
    "op-source": "audit",
    "error": "...",
    "trace-id": "a1d4334e75f94c19af18e9ede3c4****",
    "span-id": "7ec03605fe35****",
    "trace.sampled": true,
    ...
}
``` 

The structure could be:
```yaml
app_json:
  app-name:
    - hiveworker
    - kormorant
  who:
    - workers
  operation-source:
    - activitychange
    - peopleprovision
  operation-type:
    - ChangeEvent
    - audit-container
    - audit-container-content
  op-source:
    - audit
    - activitychange
    - auditcontainer
  trace-id: []
  span-id: []
```

Even when the field doesn't have any value suggesitons, keeping the key in suggestion could be helpful for the future. E.g. Keep the `trace-id` field suggestion so it'd be quicker to paste a trace ID after the field name is auto completed.

### indexes, custom_fields, and namespaces

These values are typically fetched from Sumo Logic API, or k8s API and cached.
But if you don't get the permission to either one of them, e.g. no permission to get the access ID and key for Sumo API. It's still possible to provide the suggestions in the config file.

The order of suggestion sources are:
1. API if Sumo keys and K8s config are provided.
2. Cached values if they were retrieved from API before.
3. Config values if the values weren't available in the local DB file.

