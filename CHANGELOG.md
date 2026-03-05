# CHANGELOG


## v2.1.4 (2026-03-05)

### Build System

- Refresh test deps for python 3.14
  ([`1fdce7e`](https://github.com/teh-hippo/ha-govee-led-ble/commit/1fdce7ed9f70a2a30df6c20bdcde00807bb4cee1))

### Continuous Integration

- Harden dependabot and release flow
  ([`fe9416b`](https://github.com/teh-hippo/ha-govee-led-ble/commit/fe9416b645678232cae0ef70e3b10eb6ba0d1312))


## v2.1.3 (2026-03-05)

### Bug Fixes

- Scope major-update label creation to repository
  ([`163c3bb`](https://github.com/teh-hippo/ha-govee-led-ble/commit/163c3bb8d5204d182d8689a4781840d877a734ed))


## v2.1.2 (2026-03-05)

### Bug Fixes

- Bootstrap major-update label in dependabot workflow
  ([`be88331`](https://github.com/teh-hippo/ha-govee-led-ble/commit/be8833183fcce6bd8a51d1889439635d88748ed5))


## v2.1.1 (2026-03-05)

### Bug Fixes

- Correct Copilot reviewer login
  ([`76e8376`](https://github.com/teh-hippo/ha-govee-led-ble/commit/76e8376216870b52dc203b62ac92f62de739e6ab))


## v2.1.0 (2026-03-05)

### Documentation

- Simplify README, replace table with concise list
  ([`13bf628`](https://github.com/teh-hippo/ha-govee-led-ble/commit/13bf62893beb238212e3e546c86ca3d3765e905e))

### Features

- Add local brand assets and Python 3.14 support
  ([`d66495d`](https://github.com/teh-hippo/ha-govee-led-ble/commit/d66495dab6cfe75f2130e36234badd26a4adc910))


## v2.0.7 (2026-03-01)

### Bug Fixes

- Trigger patch release for H617A retention fix
  ([`d5ccddf`](https://github.com/teh-hippo/ha-govee-led-ble/commit/d5ccddfaee5397c81ac9130321b93ecfcfd1f2bb))


## v2.0.6 (2026-03-01)

### Bug Fixes

- Normalize config-flow addresses
  ([`0f7ef95`](https://github.com/teh-hippo/ha-govee-led-ble/commit/0f7ef959977185c08c9dd11fb34a9f038baf2888))

### Documentation

- Add copilot instructions for this repo
  ([`7f38c0c`](https://github.com/teh-hippo/ha-govee-led-ble/commit/7f38c0c7d14392461f59e8bc571f9b24a77d6848))

### Testing

- Improve uncovered edge coverage
  ([`a657b42`](https://github.com/teh-hippo/ha-govee-led-ble/commit/a657b42ec1332b0b59804185c8945bc75a2e9473))


## v2.0.5 (2026-03-01)

### Build System

- Cap pytest range for Dependabot resolver
  ([`2c0d257`](https://github.com/teh-hippo/ha-govee-led-ble/commit/2c0d2576483ec3c4c6bfd79d35aecf647537e4eb))

### Continuous Integration

- Ignore ruff in Dependabot uv updates
  ([`bb6e1d5`](https://github.com/teh-hippo/ha-govee-led-ble/commit/bb6e1d5c424950a92f1ec12d86f7fa2d604ba510))


## v2.0.4 (2026-03-01)

### Build System

- Constrain coverage for uv resolver stability
  ([`2d60db9`](https://github.com/teh-hippo/ha-govee-led-ble/commit/2d60db96d605eb0f7a3757f9acddf582fc58dfe0))

### Chores

- Bound python compatibility for lock resolution
  ([`de1bfea`](https://github.com/teh-hippo/ha-govee-led-ble/commit/de1bfea2fdc72741c7faa72780f9b052e0398788))

- Sync uv.lock project version
  ([`8882e30`](https://github.com/teh-hippo/ha-govee-led-ble/commit/8882e305875ab046364c8ea758dea87157c9f4ac))


## v2.0.3 (2026-02-28)

### Bug Fixes

- Normalize H617A effects and parse scene status
  ([`469742b`](https://github.com/teh-hippo/ha-govee-led-ble/commit/469742b617b23a5d38e7fb0201168c0a116c17c5))

### Continuous Integration

- Publish latest release alias
  ([`75cfd40`](https://github.com/teh-hippo/ha-govee-led-ble/commit/75cfd40fcdd0d7b2a0f17ae49e55663a5fc71e16))


## v2.0.2 (2026-02-26)

### Bug Fixes

- Restore white-balance number value
  ([`4202d66`](https://github.com/teh-hippo/ha-govee-led-ble/commit/4202d66a78744119322ef375242d2791c99265a7))

### Continuous Integration

- Update latest tag during release
  ([`d535fba`](https://github.com/teh-hippo/ha-govee-led-ble/commit/d535fbadcc08e47725c812f7eff253a5764f8bc0))


## v2.0.1 (2026-02-24)

### Bug Fixes

- **light**: Remove invalid ONOFF color mode
  ([`766bfa8`](https://github.com/teh-hippo/ha-govee-led-ble/commit/766bfa8897b4a178c292ab8d3676c7cdbee9e0f1))


## v2.0.0 (2026-02-23)

### Refactoring

- Remove static white balance number
  ([`2e16788`](https://github.com/teh-hippo/ha-govee-led-ble/commit/2e1678824f720d637dd5d7729d03286989f579a3))

### Breaking Changes

- The white_brightness number entity is no longer created; existing entities are cleaned up from the
  entity registry on startup.


## v1.13.0 (2026-02-23)

### Chores

- Support iOS .pklg captures
  ([`154f9e9`](https://github.com/teh-hippo/ha-govee-led-ble/commit/154f9e9a9cbec3d58e4ab4645113aea947f6fea4))

### Features

- Add DreamView white balance control
  ([`9ce743e`](https://github.com/teh-hippo/ha-govee-led-ble/commit/9ce743ec28f8e2d8540e889a38e6358b2b6bd225))


## v1.12.4 (2026-02-22)

### Bug Fixes

- Expose last AA05 in diagnostics
  ([`c3c5ce7`](https://github.com/teh-hippo/ha-govee-led-ble/commit/c3c5ce7ab2503d8f991d8bb72f173edf05d26859))

### Chores

- Add diagnostics AA05 extractor
  ([`3b7e799`](https://github.com/teh-hippo/ha-govee-led-ble/commit/3b7e7993128a32c5b722010baa07c9c9eec68d7f))

- Add packet trace tooling
  ([`ac7e7e2`](https://github.com/teh-hippo/ha-govee-led-ble/commit/ac7e7e2ca1d0e53fb8a9675e22d4795409b1909e))


## v1.12.3 (2026-02-22)

### Bug Fixes

- **h6199**: Treat white setting as balance, not brightness
  ([`8f1be35`](https://github.com/teh-hippo/ha-govee-led-ble/commit/8f1be357f96eec2248226612ba06e8bc91805ad3))


## v1.12.2 (2026-02-22)

### Bug Fixes

- **h6199**: Cleanup stale controls and apply updates reliably
  ([`e58f334`](https://github.com/teh-hippo/ha-govee-led-ble/commit/e58f3347fea987c1b06d2a87edc62227adf6f9fb))


## v1.12.1 (2026-02-22)

### Bug Fixes

- **h6199**: Make video saturation reapply deterministic
  ([`02d73c2`](https://github.com/teh-hippo/ha-govee-led-ble/commit/02d73c2ff00263c4453bf75c70d064f2b37532ad))

- **h6199**: Normalize white brightness payload semantics
  ([`1a186f6`](https://github.com/teh-hippo/ha-govee-led-ble/commit/1a186f696256e4c3e2fc1cc05084ec9210366ad4))

### Refactoring

- **h6199**: Remove duplicated video brightness control
  ([`a97c286`](https://github.com/teh-hippo/ha-govee-led-ble/commit/a97c28683c9c680fb38b00c3baff3ae874384e1d))


## v1.12.0 (2026-02-22)

### Features

- Expose model music control entities
  ([`397e81d`](https://github.com/teh-hippo/ha-govee-led-ble/commit/397e81deb6cd5d7bab335e92caba85f4bdfcdd4c))


## v1.11.0 (2026-02-22)

### Features

- Enable H617A music controls
  ([`3d3f416`](https://github.com/teh-hippo/ha-govee-led-ble/commit/3d3f416f1eb6258c582f9a26e79b76acda612aca))


## v1.10.0 (2026-02-22)

### Bug Fixes

- Finalize H6199 control updates
  ([`04f31b7`](https://github.com/teh-hippo/ha-govee-led-ble/commit/04f31b75a8ceae680a56b053fe8ae2a685e3fa72))

### Features

- Add H6199 calm rhythm controls
  ([`ba44736`](https://github.com/teh-hippo/ha-govee-led-ble/commit/ba44736ad2e24daf9b1c890347b436d217c74546))

- Expand H6199 parameter support
  ([`9638d48`](https://github.com/teh-hippo/ha-govee-led-ble/commit/9638d4813d966baaa3d5478bd79c8eefd92f51fa))


## v1.9.0 (2026-02-22)

### Features

- Enable H617A state reading
  ([`3c44554`](https://github.com/teh-hippo/ha-govee-led-ble/commit/3c44554bad36afa3bda9bc8b47c99e68cb5d60b4))


## v1.8.1 (2026-02-22)

### Bug Fixes

- Align HACS display naming metadata
  ([`b4e28a5`](https://github.com/teh-hippo/ha-govee-led-ble/commit/b4e28a5f92a29fb4906256324e8d96cd036065d2))

### Chores

- Align integration naming labels
  ([`7eefcbe`](https://github.com/teh-hippo/ha-govee-led-ble/commit/7eefcbe2d1b34f063c314d3936ee2cdd2b3f018b))

### Refactoring

- Simplify BLE source paths
  ([`60c619f`](https://github.com/teh-hippo/ha-govee-led-ble/commit/60c619fa19e6b8c559498f5cac74278db46cffea))

- Simplify H6199 controls and scene data
  ([`2a07250`](https://github.com/teh-hippo/ha-govee-led-ble/commit/2a07250cd0a892385832bf62d270c50a7e1077c9))

- Tighten core BLE source paths
  ([`bb6b54f`](https://github.com/teh-hippo/ha-govee-led-ble/commit/bb6b54f28ff11d0cfc1427660db6843cc655e1f6))


## v1.8.0 (2026-02-21)

### Features

- Rename integration to ha-govee-led-ble
  ([`53d9e89`](https://github.com/teh-hippo/ha-govee-led-ble/commit/53d9e89d6d76267d6434ee6ea8cd9d03a82f9e73))


## v1.7.1 (2026-02-21)

### Bug Fixes

- **ci**: Detect Copilot review outcome via body text, not review state
  ([`8ee8d76`](https://github.com/teh-hippo/ha-govee-led-ble/commit/8ee8d76d73c7e48f71f9cdf31b7162c999f4b5ce))

### Continuous Integration

- Add copilot/dependabot push triggers, concurrency, devcontainer, and auto-merge flow
  ([`7d89542`](https://github.com/teh-hippo/ha-govee-led-ble/commit/7d89542a8e5054762eedc6ac64b5f7cfd8a768a3))


## v1.7.0 (2026-02-19)

### Bug Fixes

- Add formatted runtime translations
  ([`c8e9539`](https://github.com/teh-hippo/ha-govee-led-ble/commit/c8e9539d4994424b494d4f0ae18806202bd6e1c9))

- Add service validation placeholders
  ([`8686ff6`](https://github.com/teh-hippo/ha-govee-led-ble/commit/8686ff62e2aefb8efb080b16bc2a36dab6b5e946))

- Keep optional name arg compatibility
  ([`57269ba`](https://github.com/teh-hippo/ha-govee-led-ble/commit/57269ba813538d48dbaaf743d3625a977111c886))

- Use translation keys for parameter entities
  ([`31acd51`](https://github.com/teh-hippo/ha-govee-led-ble/commit/31acd517618f7d279f5026a1f0b2e4e97ece4be9))

### Chores

- Refresh uv lockfile
  ([`a41dc69`](https://github.com/teh-hippo/ha-govee-led-ble/commit/a41dc6946fc57c8d79f30b773d314ef3f0b7ade8))

### Continuous Integration

- Minimal 4-line .gitignore
  ([`3f50c9b`](https://github.com/teh-hippo/ha-govee-led-ble/commit/3f50c9ba44310e1b220b0e60f6865e77cf4e24c1))

### Documentation

- Standardize section naming
  ([`2e11868`](https://github.com/teh-hippo/ha-govee-led-ble/commit/2e11868c2716b81b7fedf25eba517491bc8ef694))

- Standardize status badge set
  ([`c667bcc`](https://github.com/teh-hippo/ha-govee-led-ble/commit/c667bcccaf62087e6ac1a12c450111e36eb8a0a5))

### Features

- Add diagnostics endpoint
  ([`a245df0`](https://github.com/teh-hippo/ha-govee-led-ble/commit/a245df0493162577b3fe7104bd041b72fd144784))

- Add entity icon mappings
  ([`a7bd668`](https://github.com/teh-hippo/ha-govee-led-ble/commit/a7bd668c9535a59631923011258abe9fc4831684))

- Add quality scale declaration
  ([`ffb9749`](https://github.com/teh-hippo/ha-govee-led-ble/commit/ffb97498fb5d49bd3808b2cc948de4932f030bfa))

- Declare integration logger namespaces
  ([`a481ae6`](https://github.com/teh-hippo/ha-govee-led-ble/commit/a481ae6c7fff04094fdde5cfed7ea1b461a60077))

- Declare parallel updates for platforms
  ([`312790a`](https://github.com/teh-hippo/ha-govee-led-ble/commit/312790a2e88833fae5aea780e268a0dd39c9292a))

### Refactoring

- Add coverage config section
  ([`9dfa8eb`](https://github.com/teh-hippo/ha-govee-led-ble/commit/9dfa8ebad3c640b95d5c1a08a7df300f42526b3a))

- Drop redundant mypy warn_return_any
  ([`49cdce7`](https://github.com/teh-hippo/ha-govee-led-ble/commit/49cdce7320a7ad186a99b307ca19f69e06ba0504))

- Simplify hacs metadata
  ([`5aafe9e`](https://github.com/teh-hippo/ha-govee-led-ble/commit/5aafe9eb3e893af6b0572108e65d8abd23a847e1))


## v1.6.1 (2026-02-18)

### Bug Fixes

- Standardise CI tooling to uv, ruff, mypy strict; correct type annotations
  ([`73a0198`](https://github.com/teh-hippo/ha-govee-led-ble/commit/73a0198e146df2c0bbb7e391fe522405566574dc))

### Continuous Integration

- Standardise tooling — uv, ruff, mypy strict, PSR, dependabot
  ([`32a05dc`](https://github.com/teh-hippo/ha-govee-led-ble/commit/32a05dcfaec588ec245be4f8ebd724d181089005))


## v1.6.0 (2026-02-19)

### Refactoring

- Aggressive codebase reduction — 2864 to 1996 lines (30%)
  ([`5911c75`](https://github.com/teh-hippo/ha-govee-led-ble/commit/5911c757eaeb016719adccbdb516e75e8e6ebc38))


## v1.5.0 (2026-02-19)

### Refactoring

- Reduce codebase by 30% (4098→2864 lines)
  ([`77c11e3`](https://github.com/teh-hippo/ha-govee-led-ble/commit/77c11e3ca1ebc25624f5d999b91b71d17c5f3571))


## v1.4.1 (2026-02-19)

### Chores

- Add preflight script mirroring CI checks
  ([`6071c6c`](https://github.com/teh-hippo/ha-govee-led-ble/commit/6071c6c6519b7c8b491d9456c1049baa9404ada3))


## v1.4.0 (2026-02-19)

### Bug Fixes

- Ruff format + restore HACS continue-on-error until brands PR
  ([`9c605c8`](https://github.com/teh-hippo/ha-govee-led-ble/commit/9c605c81578e743e4338f067f71072c850bf7b0c))

### Continuous Integration

- Ignore HACS brands check until registered upstream
  ([`30d999f`](https://github.com/teh-hippo/ha-govee-led-ble/commit/30d999ff2ea0607f9376e4c707003dc0310c379b))

- Pass GITHUB_TOKEN to release action explicitly
  ([`06212d3`](https://github.com/teh-hippo/ha-govee-led-ble/commit/06212d3d7f722f33b1f453863ea7cec15029a220))

### Documentation

- Tighten README — badges, device table, release flow
  ([`a2c725c`](https://github.com/teh-hippo/ha-govee-led-ble/commit/a2c725c1e5bec915b68e5c1e560b67fb14e51c7f))

### Refactoring

- Comprehensive quality uplift across HA patterns, tests, and CI
  ([`152685d`](https://github.com/teh-hippo/ha-govee-led-ble/commit/152685df0b3f9e4c37787b47772a56895c17e105))


## v1.3.3 (2026-02-18)

### Chores

- Prefer managed Python 3.13
  ([`9240ca0`](https://github.com/teh-hippo/ha-govee-led-ble/commit/9240ca02c23cf2c879704d621d2c1db8a0adab27))


## v1.3.2 (2026-02-13)

### Features

- **h6199**: Add white brightness control
  ([`9085381`](https://github.com/teh-hippo/ha-govee-led-ble/commit/90853814a59b1e6833bad2bb0dd976eb076d5397))


## v1.3.1 (2026-02-13)

### Bug Fixes

- **ci**: Format code and release v1.3.1
  ([`668c9b1`](https://github.com/teh-hippo/ha-govee-led-ble/commit/668c9b153e939a893b048f75cefad50514234dc1))


## v1.3.0 (2026-02-13)

### Features

- **h6199**: Add per-effect helper UX and release v1.3.0
  ([`72e7019`](https://github.com/teh-hippo/ha-govee-led-ble/commit/72e7019303dcfcc983dac7c77854993067f5b0db))


## v1.2.1 (2026-02-13)

### Bug Fixes

- **ci**: Run dependabot updates daily
  ([`924b73c`](https://github.com/teh-hippo/ha-govee-led-ble/commit/924b73cb43110f88c6fad582e59e61c22d407e2d))


## v1.2.0 (2026-02-12)

### Refactoring

- Remove more dead code and redundant tests
  ([`fa7d449`](https://github.com/teh-hippo/ha-govee-led-ble/commit/fa7d44902bec3573ee08d1285822b3771e0448da))


## v1.1.0 (2026-02-12)

- Initial Release
