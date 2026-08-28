SHELL := /usr/bin/env bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := build

PYTHON ?= python3
NODE := node
NPM := npm

BUILD_DIR := .build
DIST_DIR := dist
INTEGRATION_DIR := custom_components/ha_govee_led_ble
PROTOCOL_DIR := $(INTEGRATION_DIR)/generated_protocol
FRONTEND_OUTPUT_DIR := $(INTEGRATION_DIR)/frontend

PROTOCOL_ROOTS_FILE := scripts/kaitai-runtime-roots.txt
PROTOCOL_OUTPUTS_FILE := scripts/kaitai-runtime-outputs.txt
PROTOCOL_OUTPUT_NAMES := $(shell sed -e '/^[[:space:]]*$$/d' -e '/^[[:space:]]*#/d' $(PROTOCOL_OUTPUTS_FILE))
PROTOCOL_OUTPUTS := $(addprefix $(PROTOCOL_DIR)/,$(PROTOCOL_OUTPUT_NAMES))
PROTOCOL_INPUTS := $(sort $(wildcard tools/ble/kaitai/*.ksy)) scripts/generate-kaitai.sh $(PROTOCOL_ROOTS_FILE) $(PROTOCOL_OUTPUTS_FILE) mise.toml Makefile

FRONTEND_MANIFEST := $(FRONTEND_OUTPUT_DIR)/manifest.json
FRONTEND_BOOTSTRAP := $(FRONTEND_OUTPUT_DIR)/effect-studio-bootstrap.js
FRONTEND_CHUNK_NAMES := $(shell \
	python3 -c 'import json, pathlib; path = pathlib.Path("$(FRONTEND_MANIFEST)"); print(" ".join(json.loads(path.read_text()).get("chunks", [])) if path.is_file() else "")' \
	2>/dev/null)
FRONTEND_CHUNKS := $(addprefix $(FRONTEND_OUTPUT_DIR)/,$(FRONTEND_CHUNK_NAMES))
FRONTEND_OUTPUTS := $(FRONTEND_BOOTSTRAP) $(FRONTEND_CHUNKS) $(FRONTEND_MANIFEST)
FRONTEND_NODE_MODULES_LOCK := frontend/node_modules/.package-lock.json
FRONTEND_SOURCE := $(shell find frontend/src -type f -print | LC_ALL=C sort)
FRONTEND_CONFIG := frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/vite.dev.config.ts frontend/vitest.config.ts
FRONTEND_CONTRACTS := \
	frontend/src/contracts.ts \
	frontend/tests/fixtures/backend-contracts.json \
	tools/generate_frontend_contract_fixtures.py \
	$(INTEGRATION_DIR)/const.py \
	$(INTEGRATION_DIR)/effect_catalogue.py \
	$(INTEGRATION_DIR)/effect_contracts.py \
	$(INTEGRATION_DIR)/effect_deployments.py \
	$(INTEGRATION_DIR)/effect_domain.py \
	$(INTEGRATION_DIR)/effect_identity.py \
	$(INTEGRATION_DIR)/effect_migration.py \
	$(INTEGRATION_DIR)/effect_scene_defaults.py \
	$(INTEGRATION_DIR)/effect_preview.py \
	$(INTEGRATION_DIR)/effect_scenes.py \
	$(INTEGRATION_DIR)/effect_storage.py \
	$(INTEGRATION_DIR)/effect_websocket_payloads.py \
	$(INTEGRATION_DIR)/scenes.py \
	$(wildcard $(INTEGRATION_DIR)/scene_catalogues/*.json)
FRONTEND_INPUTS := $(sort $(FRONTEND_SOURCE) $(FRONTEND_CONFIG) $(FRONTEND_CONTRACTS) scripts/generate-frontend.sh .node-version mise.toml Makefile)

PACKAGE_PATH := $(DIST_DIR)/ha_govee_led_ble.zip

.PHONY: protocol frontend build check package clean verify-node verify-kaitai verify-protocol verify-frontend verify-generated

verify-node:
	@expected="$$(cat .node-version)"; actual="$$($(NODE) --version)"; \
		[[ "$$actual" == "v$$expected" ]] || { echo "Node.js $$expected is required; found $$actual" >&2; exit 1; }
	@$(NPM) --version >/dev/null

verify-kaitai:
	@bash scripts/generate-kaitai.sh verify >/dev/null

$(PROTOCOL_OUTPUTS) &: $(PROTOCOL_INPUTS) | verify-kaitai
	bash scripts/generate-kaitai.sh runtime

protocol: verify-kaitai $(PROTOCOL_OUTPUTS)

$(FRONTEND_NODE_MODULES_LOCK): frontend/package.json frontend/package-lock.json .node-version | verify-node
	$(NPM) --prefix frontend ci --ignore-scripts

$(FRONTEND_OUTPUTS) &: $(FRONTEND_INPUTS) $(FRONTEND_NODE_MODULES_LOCK) | verify-node
	bash scripts/generate-frontend.sh

frontend: verify-node $(FRONTEND_OUTPUTS)

build: protocol frontend

verify-protocol: protocol
	rm -rf $(BUILD_DIR)/verify-protocol
	mkdir -p $(BUILD_DIR)/verify-protocol
	bash scripts/generate-kaitai.sh all $(BUILD_DIR)/verify-protocol/all >/dev/null
	KAITAI_GENERATED_DIR=$(BUILD_DIR)/verify-protocol/all uv run --no-sync pytest tests/test_kaitai_protocol.py -q
	bash scripts/generate-kaitai.sh runtime $(BUILD_DIR)/verify-protocol/runtime >/dev/null
	LC_ALL=C diff --brief --recursive --no-dereference --exclude='__pycache__' $(BUILD_DIR)/verify-protocol/runtime $(PROTOCOL_DIR)

verify-frontend: frontend
	uv run --no-sync python -m tools.generate_frontend_contract_fixtures --check
	rm -rf $(BUILD_DIR)/verify-frontend
	mkdir -p $(BUILD_DIR)/verify-frontend
	bash scripts/generate-frontend.sh $(BUILD_DIR)/verify-frontend/runtime >/dev/null
	LC_ALL=C diff --brief --recursive --no-dereference --exclude='editor-loader.js' --exclude='editor.js' $(BUILD_DIR)/verify-frontend/runtime $(FRONTEND_OUTPUT_DIR)

verify-generated: verify-protocol verify-frontend

check:
	uv sync --locked
	$(MAKE) --no-print-directory build
	$(NPM) --prefix frontend run typecheck
	$(MAKE) --no-print-directory verify-frontend
	$(NPM) --prefix frontend run test:unit
	$(NPM) --prefix frontend run test:browser
	uv run --no-sync ruff check .
	uv run --no-sync ruff format --check .
	$(MAKE) --no-print-directory verify-protocol
	uv run --no-sync mypy custom_components/ha_govee_led_ble tests
	uv run --no-sync coverage run -m pytest tests/ -v --tb=short
	uv run --no-sync coverage report --precision=2 --include='custom_components/ha_govee_led_ble/*'
	@printf '\nAll checks passed.\n'

package: build verify-generated
	$(PYTHON) scripts/package.py --source $(INTEGRATION_DIR) --output $(PACKAGE_PATH)

clean:
	rm -rf $(BUILD_DIR) $(DIST_DIR)
	rm -f $(PROTOCOL_OUTPUTS) $(FRONTEND_OUTPUTS)
