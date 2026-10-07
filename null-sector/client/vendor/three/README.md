# Vendored three.js r186 (MIT, see LICENSE)

Copied from the `three@0.186.1` npm package so the game runs offline with no CDN:
`build/three.module.js`, `build/three.core.js`, and a subset of `examples/jsm` under `addons/`.
`index.html` maps the bare specifiers with an import map:

```json
{ "imports": { "three": "/vendor/three/three.module.js", "three/addons/": "/vendor/three/addons/" } }
```

To upgrade: `npm pack three@<version>`, copy the same files, and re-run the browser tests.
