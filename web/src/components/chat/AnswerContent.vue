<script setup lang="ts">
import { computed } from 'vue'

import {
  parseAnswerLines,
  parseAnswerSegments,
  type AnswerLine,
} from '@/utils/chat'

const props = withDefaults(
  defineProps<{
    answer: string
    citationIds?: number[]
  }>(),
  { citationIds: () => [] },
)

const emit = defineEmits<{
  citation: [citationId: number]
}>()

const lines = computed(() => parseAnswerLines(props.answer))
const availableCitations = computed(() => new Set(props.citationIds))

function lineTag(line: AnswerLine): string {
  if (line.kind !== 'heading') return 'p'
  return line.level === 1 ? 'h2' : line.level === 2 ? 'h3' : 'h4'
}

function openCitation(citationId: number | null): void {
  if (citationId !== null && availableCitations.value.has(citationId)) {
    emit('citation', citationId)
  }
}
</script>

<template>
  <div class="answer-content">
    <component
      :is="lineTag(line)"
      v-for="(line, lineIndex) in lines"
      :key="`${lineIndex}-${line.text}`"
      :class="['answer-line', `is-${line.kind}`]"
    >
      <span v-if="line.prefix" class="list-prefix">{{ line.prefix }}</span>
      <span class="line-copy">
        <template
          v-for="(segment, segmentIndex) in parseAnswerSegments(line.text)"
          :key="`${lineIndex}-${segmentIndex}`"
        >
          <strong v-if="segment.kind === 'strong'">{{ segment.text }}</strong>
          <code v-else-if="segment.kind === 'code'">{{ segment.text }}</code>
          <button
            v-else-if="
              segment.kind === 'citation' &&
                segment.citationId !== null &&
                availableCitations.has(segment.citationId)
            "
            type="button"
            class="citation-link"
            :aria-label="`查看引用 ${segment.citationId}`"
            @click="openCitation(segment.citationId)"
          >
            {{ segment.text }}
          </button>
          <span v-else>{{ segment.text }}</span>
        </template>
      </span>
    </component>
  </div>
</template>

<style scoped>
.answer-content {
  color: var(--ink-900);
  line-height: 1.8;
}

.answer-line {
  margin: 0 0 10px;
}

.answer-line:last-child {
  margin-bottom: 0;
}

h2.answer-line,
h3.answer-line,
h4.answer-line {
  margin-top: 18px;
  color: var(--ink-950);
  font-weight: 700;
  line-height: 1.45;
}

h2.answer-line {
  font-size: 19px;
}

h3.answer-line {
  font-size: 17px;
}

h4.answer-line {
  font-size: 15px;
}

.is-unordered,
.is-ordered {
  display: flex;
  gap: 9px;
  padding-left: 5px;
}

.list-prefix {
  flex: 0 0 20px;
  color: var(--mint-700);
  font-weight: 700;
}

.line-copy {
  min-width: 0;
  white-space: pre-wrap;
}

code {
  padding: 2px 6px;
  border: 1px solid #dce7e2;
  border-radius: 5px;
  background: #f0f5f2;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 0.88em;
}

.citation-link {
  margin: 0 2px;
  padding: 1px 6px;
  border: 1px solid rgb(15 118 110 / 24%);
  border-radius: 999px;
  color: var(--mint-700);
  background: var(--mint-100);
  font-size: 0.82em;
  font-weight: 750;
  cursor: pointer;
}

.citation-link:hover,
.citation-link:focus-visible {
  border-color: var(--mint-700);
  outline: none;
}
</style>
