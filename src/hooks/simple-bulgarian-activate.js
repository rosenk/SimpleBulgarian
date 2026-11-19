#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');

// Claude Code caps hook stdout at 10,000 characters. Anything above that is
// written to a file and replaced by a preview, which defeats the hook.
const MAX_CHARS = 9500;

const FALLBACK_CONTEXT = `SIMPLE BULGARIAN SKILL ACTIVE AUTOMATICALLY

Пиши техническия текст на български по правилата на прост български език (по образеца на ASD-STE100): кратки изречения, деятелен залог, една дума за едно значение, условие преди команда, без канцеларщина. Не променяй код, идентификатори, команди и цитирани грешки.`;

const HEADER = [
  'SIMPLE BULGARIAN SKILL ACTIVE AUTOMATICALLY',
  '',
  'Спазвай тези правила за писане на български, без да чакаш потребителят да назове skill-а. Правилата важат за текст на български. За текст на друг език пиши както обикновено. Целият skill, с каталога на правилата и режима за проверка, е в skills/simple-bulgarian/SKILL.md в този plugin. Прочети го за проверка на текст или за строгия режим.',
  '',
].join('\n');

function candidates(pluginRoot, hookDirectory, relative) {
  const roots = [];
  if (pluginRoot) {
    roots.push(pluginRoot);
  }
  roots.push(path.join(hookDirectory, '..', '..'), path.join(hookDirectory, '..'));
  return roots.map((root) => path.join(root, ...relative));
}

function promptCandidates(pluginRoot, hookDirectory) {
  return candidates(pluginRoot, hookDirectory, ['prompts', 'system-prompt.md']);
}

function readFirstFile(list) {
  for (const candidate of list) {
    try {
      return fs.readFileSync(candidate, 'utf8');
    } catch (error) {
      // Missing, unreadable, or a directory: try the next candidate.
    }
  }
  return '';
}

function stripFrontmatter(content) {
  return content.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/, '');
}

// prompts/system-prompt.md is a page for people: a title, a paragraph that says
// where to paste the block, the rule block between two "---" lines, then a
// word-budget variant. The model gets the fenced block only.
function ruleBlock(content) {
  const fence = /^---[ \t]*\r?$/m;
  const first = content.search(fence);
  if (first === -1) {
    return content;
  }
  const rest = content.slice(first).replace(fence, '');
  const second = rest.search(fence);
  return second === -1 ? rest : rest.slice(0, second);
}

function buildContext(promptText) {
  if (!promptText) {
    return FALLBACK_CONTEXT;
  }
  const out = HEADER + ruleBlock(stripFrontmatter(promptText)).trim();
  if (out.length > MAX_CHARS) {
    process.stderr.write(`simple-bulgarian hook: payload is ${out.length} characters, over the ${MAX_CHARS} cap; sending the fallback ruleset\n`);
    return FALLBACK_CONTEXT;
  }
  return out;
}

function main() {
  const pluginRoot = process.env.PLUGIN_ROOT || process.env.CLAUDE_PLUGIN_ROOT;
  process.stdout.write(buildContext(readFirstFile(promptCandidates(pluginRoot, __dirname))));
}

if (require.main === module) {
  main();
}

module.exports = {
  FALLBACK_CONTEXT,
  MAX_CHARS,
  buildContext,
  promptCandidates,
  readFirstFile,
  ruleBlock,
  stripFrontmatter,
};
