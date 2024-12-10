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

<pre><code>$> sumoq -k .access_keys.yml -kc ~/.kube/config/stork-qa01-mp-npe-iad0-nc1.yaml
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

<pre><code>query> _index=qa01_mp_npe_debug _sourceName=px-1072-box-1656699
       | where %"app-name"="hiveworker" and %"trace.sampled"="true"


Copied to clipboard
</code></pre>