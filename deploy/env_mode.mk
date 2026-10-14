# Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Single source of truth for what the HUB selector means (FLIP#1479). Sibling of
# instance.mk and fl_backend.mk, included by every Makefile that reads HUB —
# root, deploy/providers/AWS, trust, trust/xnat, trust/deploy/helm,
# fl-services/{nvflare,flower}, flip-ui — at the very top, BEFORE their env-file
# include: this file needs only HUB, and the env file's name is one of the things
# it derives.
#
#   HUB        ENV          .env file          compose      ENV_CLASS
#   (unset)    development  .env.development   development  stag
#   stag       stag         .env.stag          prod         stag
#   prod       prod         .env.prod          prod         prod
#
# ENV is the token in every per-environment file name: the hub env file
# .env.$(ENV) and the trust kit files trust/.env.<CODE>.$(ENV).

# PROD was the selector until FLIP#1479. Refused rather than ignored, so an old
# command line, or a PROD still exported in the shell, cannot run against development.
ifneq ($(strip $(PROD)),)
$(error PROD is replaced by HUB (FLIP#1479): unset PROD and pass HUB=prod (was true/lza) or HUB=stag (was lza-stag); PROD=stag's self-contained staging account is retired — got PROD='$(PROD)')
endif

ifeq ($(HUB),prod)
ENV := prod
else ifeq ($(HUB),stag)
ENV := stag
else ifeq ($(strip $(HUB)),)
ENV := development
else
$(error HUB must be unset, stag or prod — got '$(HUB)')
endif

# Repo-root-relative name of the hub env file; each Makefile prefixes its own
# path to the repo root.
ENV_FILE_NAME := .env.$(ENV)
# Compose-file suffix: every deployed environment runs the prod compose.
__DCKR_SUFFIX := $(if $(filter development,$(ENV)),development,prod)
# Non-empty iff a hub is selected — usable in `ifneq` and in recipe-level
# `[ -n "$(IS_DEPLOYED)" ]` tests alike.
IS_DEPLOYED := $(strip $(HUB))
# prod | stag — the environment class Terraform, the deploy git ref and the FL
# kit CA workspace key on. Development counts as stag.
ENV_CLASS := $(if $(filter prod,$(ENV)),prod,stag)

# Pre-FLIP#1479 names, still found for one release so a live site's next upgrade does
# not break. Remove with the fallback: these two lines and the bare .env.<CODE> below.
OLD_ENV_NAMES := $(if $(filter prod,$(ENV)),lza-prod production,$(if $(filter stag,$(ENV)),lza-stag))
OLD_KIT_ENVS := $(if $(filter prod,$(ENV)),production lza-prod,$(if $(filter stag,$(ENV)),lza-stag))

# A hub env file under an old name, beside .env.$(ENV) or instead of it, stops make: two
# candidates is how a stale AES key nearly reached a site's kit. Not checked when
# MAIN_ENV_FILE names the file outright (the root Makefile passes it on to its sub-makes).
_REPO_ROOT_DIR := $(dir $(lastword $(MAKEFILE_LIST)))../
ifneq ($(and $(IS_DEPLOYED),$(filter undefined,$(origin MAIN_ENV_FILE))),)
_HUB_ENV_FILES := $(patsubst $(_REPO_ROOT_DIR)%,%,$(wildcard $(addprefix $(_REPO_ROOT_DIR).env.,$(ENV) $(OLD_ENV_NAMES))))
ifneq ($(word 2,$(_HUB_ENV_FILES)),)
$(error $(_HUB_ENV_FILES) are all hub env files for HUB=$(HUB) (FLIP#1479): keep the one holding the live values as $(ENV_FILE_NAME) and delete the others)
else ifneq ($(filter-out $(ENV_FILE_NAME),$(_HUB_ENV_FILES)),)
$(error $(_HUB_ENV_FILES) is the hub env file's pre-FLIP#1479 name: rename it to $(ENV_FILE_NAME))
endif
endif

# Kit files. A trust's kit is trust/.env.<CODE>.$(ENV), else one of its old names —
# .production / .lza-prod / a bare .env.<CODE> for prod, .lza-stag for stag.
_kit_names = $(1).env.$(2).$(ENV) $(foreach e,$(OLD_KIT_ENVS),$(1).env.$(2).$(e)) $(if $(filter prod,$(ENV)),$(1).env.$(2))
# $(call kit_file,<trust dir with trailing / or empty>,<CODE>): the one of those names
# that exists, else the current one. Two that exist stop make: only one holds the live kit.
kit_file = $(call _one_kit,$(wildcard $(call _kit_names,$(1),$(2))),$(1).env.$(2).$(ENV))
_one_kit = $(if $(word 2,$(1)),$(error $(1) are all kits for one trust (HUB=$(HUB)): keep the live one as $(2) and delete the others),$(or $(1),$(2)))
# $(call kit_codes,<trust dir>): the CODE of every kit present for this hub, under any of those names.
kit_codes = $(sort $(foreach e,$(ENV) $(OLD_KIT_ENVS),$(patsubst $(1).env.%.$(e),%,$(wildcard $(1).env.*.$(e)))) $(if $(filter prod,$(ENV)),$(call _bare_kit_codes,$(1))))
# A bare .env.<CODE> has no further dot; .env.example is the template, not a kit.
_bare_kit_codes = $(filter-out example,$(foreach c,$(patsubst $(1).env.%,%,$(wildcard $(1).env.*)),$(if $(findstring .,$(c)),,$(c))))
# $(call kit_files,<trust dir>): every such kit file, as kit_file resolves it.
kit_files = $(foreach c,$(call kit_codes,$(1)),$(call kit_file,$(1),$(c)))
# $(call old_kit_hint,<kit file>): one line asking to rename a kit found under an old name.
old_kit_hint = $(if $(filter-out %.$(ENV),$(1)),$(info ⚠️  $(1) is an old kit name — rename it to $(or $(firstword $(foreach e,$(OLD_KIT_ENVS),$(patsubst %.$(e),%.$(ENV),$(filter %.$(e),$(1))))),$(1).$(ENV))))
# $(call kit_hint,<repo-relative kit file>): old_kit_hint once per command — sub-makes
# inherit _KIT_HINTED — and never for a KIT_FILE the user named outright.
kit_hint = $(if $(filter $(1),$(_KIT_HINTED))$(filter command line environment,$(origin KIT_FILE)),,$(call old_kit_hint,$(1))$(eval export _KIT_HINTED := $(1)))
