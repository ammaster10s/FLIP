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
# Azure trust node (FLIP#1390). Every Azure-touching target needs AZ_SUBSCRIPTION (the trial
# subscription's name or id): the CLI default on the build account is a KCL subscription, so
# nothing here ever relies on it. No target skips Terraform's confirmation: apply, destroy and
# bootstrap all show the plan and ask.

SHELL := /bin/bash
TF := terraform
NAME_PREFIX ?= flipaz
# The node's region. The outbound IP follows it; the bootstrap's state storage stays in
# BOOTSTRAP_LOCATION, so moving the node replaces only the IP.
LOCATION ?= uksouth
BOOTSTRAP_LOCATION ?= uksouth
FL_BACKEND ?= nvflare
SSH_PUBLIC_KEY_FILE ?= $(HOME)/.ssh/id_ed25519.pub
FLIP_REF ?= $(shell git rev-parse HEAD)
UNIT ?= flip-provision
LINES ?= 80
# Your public IP: the kit drop's firewall admits only it and the node subnet, and the AKS API
# server only it. Looked up lazily, once per make run, so every use in a run sees the same answer.
# Only an IPv4 address (every octet 0-255) is kept, because the answer reaches a shell; a failed
# lookup is empty, and curl's own error is left on the terminal.
OCTET_PATTERN := (25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])
IPV4_PATTERN := $(OCTET_PATTERN)(\.$(OCTET_PATTERN)){3}
OPERATOR_IP ?= $(eval OPERATOR_IP := $$(shell curl -fsS --max-time 10 https://api.ipify.org | grep -Ex '$(IPV4_PATTERN)' | head -n1))$(OPERATOR_IP)

# Resolved lazily, only by the targets that need Azure, and once per make run: az given an empty
# --subscription silently uses the CLI default, so every call must get the id that was checked.
SUB_ID = $(eval SUB_ID := $$(shell az account show --subscription "$(AZ_SUBSCRIPTION)" --query id -o tsv 2>/dev/null))$(SUB_ID)
GUID_PATTERN := [0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}
BOOT = $(TF) -chdir=bootstrap output -raw
NODE_RG = $(NAME_PREFIX)-node-rg
NODE_VM = $(NAME_PREFIX)-node
AKS_RG = $(NAME_PREFIX)-aks-rg
AKS_NAME = $(NAME_PREFIX)-aks

# Destroy only deletes, so the kit drop's firewall is never applied: a documentation address
# (TEST-NET-1) satisfies the variable's check without looking the operator's IP up, so a blocked
# api.ipify.org never stands between the operator and a teardown.
DESTROY_OPERATOR_IP := 192.0.2.1

define require_subscription
	@[ -n "$(AZ_SUBSCRIPTION)" ] || { echo "❌ AZ_SUBSCRIPTION=<trial subscription name or id> is required (never the CLI default)."; exit 1; }
	@[[ "$(SUB_ID)" =~ ^$(GUID_PATTERN)$$ ]] || { echo "❌ Cannot read subscription '$(AZ_SUBSCRIPTION)'. Run: az login"; exit 1; }
endef

# Run Command: the node's only way in. flip-node does the work; long steps run as units.
define run_on_node
	az vm run-command invoke --subscription "$(SUB_ID)" -g $(NODE_RG) -n $(NODE_VM) \
		--command-id RunShellScript --scripts "$(1)" --query 'value[0].message' -o tsv
endef

# Run Command hands its script to a shell on the node, so every argument is checked here, before it
# goes into that script: flip-node's own checks run only after the node's shell has parsed it. The
# patterns are flip-node's; a value is single-quoted for the local shell while it is checked.
sq = '$(subst ','\'',$(1))'
REF_PATTERN := ([0-9a-f]{40}|v[0-9]+\.[0-9]+\.[0-9]+)
BACKEND_PATTERN := (nvflare|flower)
BLOB_PATTERN := [A-Za-z0-9][A-Za-z0-9._-]*\.tar\.gz
KIT_PATTERN := [A-Za-z0-9_]+
PROD_PATTERN := [a-z-]+
UNIT_PATTERN := [A-Za-z0-9][A-Za-z0-9@._-]*
LINES_PATTERN := [0-9]{1,5}
# $(call check_arg,<variable name>,<value>,<pattern>)
check_arg = v=$(call sq,$(2)); [[ "$$v" =~ ^$(3)$$ ]] || { echo "❌ $(1)='$$v' is not valid: it must match $(3)."; exit 1; }

# The AKS API server admits one IP, and an operator's public IP moves (home, office, VPN). This
# resets it without a plan. aks-plan passes OPERATOR_IP to Terraform the same way, so its next plan
# shows no allowlist change as long as your IP has not moved again.
define admit_operator
	az aks update --subscription "$(SUB_ID)" -g $(AKS_RG) -n $(AKS_NAME) --api-server-authorized-ip-ranges "$(OPERATOR_IP)/32"
endef

# The value is single-quoted for the local shell while it is checked, as check_arg does.
define require_operator_ip
	@v=$(call sq,$(OPERATOR_IP)); [[ "$$v" =~ ^$(IPV4_PATTERN)$$ ]] || { \
		echo "❌ OPERATOR_IP='$$v' is not one IPv4 address: the api.ipify.org lookup failed (curl's error, if any, is above) or answered something else."; \
		echo "   Pass yours: make $@ OPERATOR_IP=<your public IPv4>"; exit 1; }
endef

.PHONY: help bootstrap init plan apply destroy destroy-bootstrap status reprovision selftest kit-upload selftest-kit join aks-init aks-plan aks-apply aks-destroy aks-credentials aks-stop aks-start aks-allow-ip logs report stop start test lint

help: ## Show this help message
	@echo "FLIP Azure trust node commands:"
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?##"}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

bootstrap: ## One-off: state storage, budget alert, static outbound IP (STATE_SA=<unique name> ALERT_EMAIL=<you>)
	$(require_subscription)
	@[ -n "$(STATE_SA)" ] || { echo "❌ STATE_SA=<3-24 lowercase letters/digits, globally unique> is required."; exit 1; }
	$(TF) -chdir=bootstrap init -input=false
	$(TF) -chdir=bootstrap apply \
		-var "subscription_id=$(SUB_ID)" -var "location=$(BOOTSTRAP_LOCATION)" -var "egress_location=$(LOCATION)" \
		-var "name_prefix=$(NAME_PREFIX)" -var "state_storage_account_name=$(STATE_SA)" \
		-var "budget_start_date=$(shell date -u +%Y-%m-01T00:00:00Z)" \
		$(if $(ALERT_EMAIL),-var 'alert_emails=["$(ALERT_EMAIL)"]',-var create_budget=false)

init: ## Point the vm root at the bootstrap's state storage
	$(require_subscription)
	$(TF) -chdir=vm init -input=false -reconfigure \
		-backend-config="subscription_id=$(SUB_ID)" \
		-backend-config="resource_group_name=$$($(BOOT) resource_group_name)" \
		-backend-config="storage_account_name=$$($(BOOT) state_storage_account_name)" \
		-backend-config="container_name=$$($(BOOT) state_container_name)" \
		-backend-config="key=vm.tfstate" \
		-backend-config="use_azuread_auth=true"

plan: ## Plan the node (FLIP_REF must be pushed to GitHub)
	$(require_subscription)
	@[ -f "$(SSH_PUBLIC_KEY_FILE)" ] || { echo "❌ SSH_PUBLIC_KEY_FILE=$(SSH_PUBLIC_KEY_FILE) not found."; exit 1; }
	@git branch -r --contains "$(FLIP_REF)" | grep -q . || { echo "❌ $(FLIP_REF) is not on any pushed branch; the node clones from GitHub."; exit 1; }
	$(TF) -chdir=vm plan -out=vm.tfplan \
		-var "subscription_id=$(SUB_ID)" -var "location=$(LOCATION)" -var "name_prefix=$(NAME_PREFIX)" \
		-var "egress_public_ip_id=$$($(BOOT) egress_public_ip_id)" \
		-var "admin_ssh_public_key=$$(cat $(SSH_PUBLIC_KEY_FILE))" \
		-var "flip_ref=$(FLIP_REF)" -var "fl_backend=$(FL_BACKEND)" -var "operator_ip=$(OPERATOR_IP)"

apply: ## Show the saved plan and the target subscription, then apply it only after a typed yes
	$(require_subscription)
	$(TF) -chdir=vm show vm.tfplan
	@echo ""
	@echo "Target subscription: $$(az account show --subscription "$(SUB_ID)" --query '[name, id]' -o tsv | paste -sd ' ' -)"
	@read -r -p "Apply this plan? Type yes to continue: " answer; [ "$$answer" = "yes" ] || { echo "Not applied."; exit 1; }
	$(TF) -chdir=vm apply vm.tfplan
	@echo "Outbound IP: $$($(BOOT) egress_public_ip_address)"

destroy: ## Destroy the node, keep bootstrap and the outbound IP (asks first)
	$(require_subscription)
	$(TF) -chdir=vm destroy \
		-var "subscription_id=$(SUB_ID)" -var "location=$(LOCATION)" -var "name_prefix=$(NAME_PREFIX)" \
		-var "egress_public_ip_id=$$($(BOOT) egress_public_ip_id)" \
		-var "admin_ssh_public_key=$$(cat $(SSH_PUBLIC_KEY_FILE))" -var "flip_ref=$(FLIP_REF)" \
		-var "operator_ip=$(DESTROY_OPERATOR_IP)"

destroy-bootstrap: ## Destroy everything bootstrap made (refuses while the node exists; asks first)
	$(require_subscription)
	@if [ "$$(az group exists --subscription "$(SUB_ID)" -n $(NODE_RG))" = "true" ]; then \
		echo "❌ $(NODE_RG) still exists. Run make destroy first: removing the state now would leave a node spending credit with no state."; exit 1; fi
	$(TF) -chdir=bootstrap destroy -var "subscription_id=$(SUB_ID)" \
		-var "state_storage_account_name=$$($(BOOT) state_storage_account_name)" -var create_budget=false

status: ## First-boot and provisioning state of the node
	$(require_subscription)
	@$(call run_on_node,flip-node status)

reprovision: ## Re-run the play on the node (REF=<sha|vX.Y.Z> to move the code)
	@$(if $(REF),$(call check_arg,REF,$(REF),$(REF_PATTERN)),true)
	$(require_subscription)
	@$(call run_on_node,flip-node reprovision $(REF))

selftest: ## Start the hubless self-test on the node, on the kit selftest-kit delivered (FL_BACKEND=nvflare|flower)
	@$(call check_arg,FL_BACKEND,$(FL_BACKEND),$(BACKEND_PATTERN))
	$(require_subscription)
	@$(call run_on_node,flip-node selftest $(FL_BACKEND))

kit-upload: ## Put a kit tarball in the node's kit drop (TARBALL=<path> [NAME=<blob name>]); deleted within about 48 hours
	$(require_subscription)
	@[ -f "$(TARBALL)" ] || { echo "❌ TARBALL=<path to a kit tarball> is required."; exit 1; }
	@$(call check_arg,NAME,$(or $(NAME),$(notdir $(TARBALL))),$(BLOB_PATTERN))
	@url=$$($(TF) -chdir=vm output -raw kit_drop_url 2>/dev/null); \
	[ -n "$$url" ] || { echo "❌ No kit drop: apply the vm root with kit_drop_enabled=true first."; exit 1; }; \
	az storage blob upload --subscription "$(SUB_ID)" --auth-mode login --overwrite --only-show-errors --no-progress \
		--blob-url "$$url/$(or $(NAME),$(notdir $(TARBALL)))" --file "$(TARBALL)" -o none || { \
		echo "❌ Upload refused. A 403 usually means your IP ($(OPERATOR_IP)) is not the one the kit drop's firewall allows"; \
		echo "   (re-run make plan && make apply to update it), or your role assignment is still propagating."; exit 1; }; \
	echo "✅ Uploaded as $(or $(NAME),$(notdir $(TARBALL))); the blob is deleted within about 48 hours (a day, plus up to a day for Azure's daily lifecycle run)."

selftest-kit: ## Pack a self-test FL kit here and put it in the kit drop (FL_BACKEND=nvflare|flower)
	@$(call check_arg,FL_BACKEND,$(FL_BACKEND),$(BACKEND_PATTERN))
	bash scripts/pack-selftest-kit.sh $(FL_BACKEND) build/selftest-$(FL_BACKEND).tar.gz
	$(MAKE) kit-upload TARBALL=build/selftest-$(FL_BACKEND).tar.gz NAME=selftest-$(FL_BACKEND).tar.gz
	@rm -f build/selftest-$(FL_BACKEND).tar.gz

join: ## Install a hub-registered kit on the node and bring the trust up (NAME=<blob> KIT=<code> PROD=lza-stag)
	$(require_subscription)
	@[ -n "$(NAME)" ] && [ -n "$(KIT)" ] && [ -n "$(PROD)" ] || { echo "❌ NAME=<uploaded kit blob> KIT=<trust code> PROD=<env> are required."; exit 1; }
	@$(call check_arg,NAME,$(NAME),$(BLOB_PATTERN))
	@$(call check_arg,KIT,$(KIT),$(KIT_PATTERN))
	@$(call check_arg,PROD,$(PROD),$(PROD_PATTERN))
	@$(call run_on_node,flip-node join $(NAME) $(KIT) $(PROD))

logs: ## Tail a node unit's log (UNIT=flip-selftest-nvflare LINES=80)
	@$(call check_arg,UNIT,$(UNIT),$(UNIT_PATTERN))
	@$(call check_arg,LINES,$(LINES),$(LINES_PATTERN))
	$(require_subscription)
	@$(call run_on_node,flip-node logs $(UNIT) $(LINES))

report: ## Print the latest self-test report (FL_BACKEND=nvflare|flower)
	@$(call check_arg,FL_BACKEND,$(FL_BACKEND),$(BACKEND_PATTERN))
	$(require_subscription)
	@$(call run_on_node,flip-node report $(FL_BACKEND))

stop: ## Deallocate the VM (compute stops billing; disks and IP stay)
	$(require_subscription)
	az vm deallocate --subscription "$(SUB_ID)" -g $(NODE_RG) -n $(NODE_VM)

start: ## Start a deallocated VM
	$(require_subscription)
	az vm start --subscription "$(SUB_ID)" -g $(NODE_RG) -n $(NODE_VM)

# ── AKS: the same trust on a one-node managed cluster (the flip-trust chart) ─────────────────
# The cluster's load balancer egresses from the bootstrap IP, which the VM's NIC holds in
# public_ip mode, and the trial quota fits one 4-vCPU node: never run the two together.

aks-init: ## Point the aks root at the bootstrap's state storage
	$(require_subscription)
	$(TF) -chdir=aks init -input=false -reconfigure \
		-backend-config="subscription_id=$(SUB_ID)" \
		-backend-config="resource_group_name=$$($(BOOT) resource_group_name)" \
		-backend-config="storage_account_name=$$($(BOOT) state_storage_account_name)" \
		-backend-config="container_name=$$($(BOOT) state_container_name)" \
		-backend-config="key=aks.tfstate" \
		-backend-config="use_azuread_auth=true"

aks-plan: ## Plan the AKS cluster (its API server admits only your IP)
	$(require_subscription)
	$(TF) -chdir=aks plan -out=aks.tfplan \
		-var "subscription_id=$(SUB_ID)" -var "location=$(LOCATION)" -var "name_prefix=$(NAME_PREFIX)" \
		-var "egress_public_ip_id=$$($(BOOT) egress_public_ip_id)" -var "operator_ip=$(OPERATOR_IP)"

aks-apply: ## Show the saved AKS plan and the subscription, then apply it only after a typed yes
	$(require_subscription)
	@if [ "$$(az group exists --subscription "$(SUB_ID)" -n $(NODE_RG))" = "true" ]; then \
		echo "❌ $(NODE_RG) exists: the VM holds the outbound IP and the trial's vCPUs. make destroy first."; exit 1; fi
	$(TF) -chdir=aks show aks.tfplan
	@echo ""
	@echo "Target subscription: $$(az account show --subscription "$(SUB_ID)" --query '[name, id]' -o tsv | paste -sd ' ' -)"
	@read -r -p "Apply this plan? Type yes to continue: " answer; [ "$$answer" = "yes" ] || { echo "Not applied."; exit 1; }
	$(TF) -chdir=aks apply aks.tfplan

aks-destroy: ## Destroy the AKS cluster, keep bootstrap and the outbound IP (asks first)
	$(require_subscription)
	$(TF) -chdir=aks destroy \
		-var "subscription_id=$(SUB_ID)" -var "location=$(LOCATION)" -var "name_prefix=$(NAME_PREFIX)" \
		-var "egress_public_ip_id=$$($(BOOT) egress_public_ip_id)" -var "operator_ip=$(DESTROY_OPERATOR_IP)"

aks-credentials: ## Fetch kubectl credentials (Entra sign-in through kubelogin)
	$(require_subscription)
	@command -v kubelogin >/dev/null || { echo "❌ kubelogin is required (brew install Azure/kubelogin/kubelogin)"; exit 1; }
	az aks get-credentials --subscription "$(SUB_ID)" -g $(AKS_RG) -n $(AKS_NAME) --overwrite-existing
	kubelogin convert-kubeconfig -l azurecli

aks-stop: ## Stop the cluster (its node stops billing; disks and the IP stay)
	$(require_subscription)
	az aks stop --subscription "$(SUB_ID)" -g $(AKS_RG) -n $(AKS_NAME)

aks-start: ## Start a stopped cluster, then admit only your current IP to its API server
	$(require_operator_ip)
	$(require_subscription)
	az aks start --subscription "$(SUB_ID)" -g $(AKS_RG) -n $(AKS_NAME)
	$(admit_operator) || { \
		echo "❌ The cluster is running (and billing), but its API server still admits only its previous IP."; \
		echo "   Retry: make aks-allow-ip AZ_SUBSCRIPTION=... Or stop it: make aks-stop AZ_SUBSCRIPTION=..."; exit 1; }

aks-allow-ip: ## Admit only your current IP to the running cluster's API server, without a plan (free)
	$(require_operator_ip)
	$(require_subscription)
	$(admit_operator)

test: ## Credential-free checks: terraform test in every root and module, plus pytest
	@for d in bootstrap modules/network modules/kit_drop vm aks; do \
		echo "── $$d"; ( cd $$d && $(TF) init -backend=false -input=false >/dev/null && $(TF) validate -no-color && $(TF) test -no-color ) || exit 1; \
	done
	uv run --no-project --with pytest pytest tests/ -q

lint: ## terraform fmt check and tflint over the Azure tree
	$(TF) fmt -check -recursive
	tflint --init --config "$(CURDIR)/.tflint.hcl" && tflint --recursive --config "$(CURDIR)/.tflint.hcl"
