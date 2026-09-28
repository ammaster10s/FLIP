<!--
    Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at
        http://www.apache.org/licenses/LICENSE-2.0
    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
-->

<!-- One project staged at the Trust Admin's trust (FLIP#1258): a summary line that expands to what the decision
     needs — owner, description, the trust's own cohort count and query, whether it has imaging — with Approve /
     Decline while it is pending. The page owns the confirmation and the call. -->
<template>
    <li data-test="decision-row" :data-project="decision.projectId" class="py-3">
        <button
            type="button"
            data-test="decision-row-toggle"
            class="flex items-center w-full gap-3 text-left group"
            :aria-expanded="open"
            @click="open = !open"
        >
            <icon-ph-caret-right
                class="w-4 h-4 text-gray-400 transition-transform shrink-0 dark:text-gray-300"
                :class="open && 'rotate-90'"
                aria-hidden="true"
            />
            <span class="min-w-0 grow">
                <span class="block text-sm font-semibold text-gray-900 truncate dark:text-gray-100 group-hover:text-primary-600">
                    {{ decision.projectName }}
                </span>
                <span class="block text-xs text-gray-500 truncate dark:text-gray-300">
                    {{ decision.ownerName ?? "Unknown owner" }}
                    <template v-if="decision.stagedAt"> · staged {{ shortDate(decision.stagedAt) }}</template>
                </span>
            </span>
            <span
                v-if="decision.status !== 'PENDING'"
                class="shrink-0 text-xs text-right text-gray-600 dark:text-gray-300"
                data-test="decision-outcome"
            >
                <span class="font-semibold" :class="decision.status === 'APPROVED' ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'">
                    {{ decision.status === "APPROVED" ? "Approved" : "Declined" }}
                </span>
                {{ decidedBy }}
            </span>
        </button>

        <div v-if="open" data-test="decision-details" class="mt-3 ml-7 space-y-3 text-sm text-gray-700 dark:text-gray-200">
            <p v-if="decision.description">
                {{ decision.description }}
            </p>
            <dl class="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
                <dt class="text-gray-500 dark:text-gray-300">
                    Cohort at {{ trustName }}
                </dt>
                <dd data-test="decision-cohort" class="font-semibold">
                    {{ cohortText }}
                </dd>
                <dt class="text-gray-500 dark:text-gray-300">
                    Imaging
                </dt>
                <dd>
                    {{ decision.hasImaging ? "Yes — approving starts the imaging pull" : "No — tabular data only" }}
                </dd>
            </dl>
            <div v-if="decision.query">
                <p class="mb-1 text-gray-500 dark:text-gray-300">
                    Cohort query
                </p>
                <pre
                    data-test="decision-query"
                    class="p-3 overflow-x-auto font-mono text-xs whitespace-pre-wrap bg-gray-50 border border-gray-200 rounded-md dark:bg-dark-canvas dark:border-dark-border"
                >{{ decision.query }}</pre>
            </div>
            <div v-if="decision.status === 'PENDING'" class="flex justify-end gap-2">
                <AiButton data-test="decline-btn" @click="emit('decide', 'decline')">
                    Decline
                </AiButton>
                <AiButton data-test="approve-btn" primary @click="emit('decide', 'approve')">
                    Approve
                </AiButton>
            </div>
        </div>
    </li>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

import AiButton from "@/components/AiButton/AiButton.vue";
import type { ITrustDecision } from "@/services/trust-service";

const props = defineProps<{
    decision: ITrustDecision;
    trustName: string;
}>();

const emit = defineEmits<{ decide: [choice: "approve" | "decline"] }>();

const open = ref(false);

const shortDate = (iso: string) =>
    new Date(iso).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric"
    });

const cohortText = computed(() => {
    const cohort = props.decision.cohort;
    if (!cohort) return "Not reported";
    if (cohort.error) return "Query failed";
    if (cohort.suppressed) return "Below the trust's disclosure threshold";

    return `${(cohort.recordCount ?? 0).toLocaleString()} records`;
});

// "by Ada Admin · 1 Sep 2026", marked "(hub)" when the hub decided before the trust had a Trust Admin.
const decidedBy = computed(() => {
    const { decidedAs, decidedByName, decidedAt } = props.decision;
    const who = decidedByName ? `by ${decidedByName}${decidedAs === "HUB" ? " (hub)" : ""}` : "";

    return [who, decidedAt ? shortDate(decidedAt) : ""].filter(Boolean).join(" · ");
});
</script>
