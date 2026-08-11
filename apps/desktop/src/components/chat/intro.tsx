import { type CSSProperties, useState } from 'react'

import { type Locale, useI18n } from '@/i18n'
import { capitalize, normalize } from '@/lib/text'

import introCopyJsonl from './intro-copy.jsonl?raw'

type IntroCopy = {
  headline: string
  body: string
  bodyZh?: string
}

type IntroCopyRecord = IntroCopy & {
  personality: string
  body_zh?: string
}

export type IntroProps = {
  personality?: string
  seed?: number
}

const NEUTRAL_PERSONALITIES = new Set(['', 'default', 'none', 'neutral'])
const CHINESE_LOCALES = new Set<Locale>(['zh', 'zh-hant'])

const FALLBACK_COPY: IntroCopy[] = [
  {
    headline: 'What are we auditing today?',
    body: "Share energy bills, equipment lists, or building data. I'll analyze consumption and identify the next saving opportunity."
  },
  {
    headline: "What's the energy challenge?",
    body: "Bring the bill, the anomaly, or the retrofit goal. I'll read the data before making recommendations."
  },
  {
    headline: 'What should we assess?',
    body: "Send the building profile, consumption curve, or audit scope. I'll help turn it into action."
  },
  {
    headline: 'Where should we start?',
    body: "Bring the problem, target, or dataset. I'll inspect first and keep the next step concrete."
  },
  {
    headline: 'What needs attention?',
    body: "Send the context you have. I'll help sort it into a plan or a saving."
  }
]

const FALLBACK_COPY_ZH: IntroCopy[] = [
  {
    headline: '今天我们要审计什么？',
    body: '分享能源账单、设备清单或建筑数据。我会分析能耗并找出下一个节能机会。'
  },
  {
    headline: '能源挑战是什么？',
    body: '带上账单、异常点或改造目标。我会先读数据再提建议。'
  },
  {
    headline: '我们应该评估什么？',
    body: '发送建筑档案、用能曲线或审计范围。我会帮你把它变成行动。'
  },
  {
    headline: '我们应该从哪里开始？',
    body: '带上问题、目标或数据集。我会先检查，并让下一步保持具体。'
  },
  {
    headline: '哪里需要注意？',
    body: '发送你已有的上下文。我会帮你整理成计划或节能方案。'
  }
]

function normalizeKey(value?: string): string {
  return normalize(value)
}

function titleize(value: string): string {
  return value
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map(capitalize)
    .join(' ')
}

function isIntroCopyRecord(value: unknown): value is IntroCopyRecord {
  if (!value || typeof value !== 'object') {
    return false
  }

  const record = value as Record<string, unknown>

  return (
    typeof record.personality === 'string' &&
    typeof record.headline === 'string' &&
    typeof record.body === 'string' &&
    (record.body_zh === undefined || typeof record.body_zh === 'string') &&
    Boolean(record.personality.trim()) &&
    Boolean(record.headline.trim()) &&
    Boolean(record.body.trim())
  )
}

function parseIntroCopy(raw: string): Record<string, IntroCopy[]> {
  const byPersonality: Record<string, IntroCopy[]> = {}

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim()

    if (!trimmed) {
      continue
    }

    try {
      const parsed: unknown = JSON.parse(trimmed)

      if (!isIntroCopyRecord(parsed)) {
        continue
      }

      const key = normalizeKey(parsed.personality)
      byPersonality[key] ??= []
      byPersonality[key].push({
        headline: parsed.headline.trim(),
        body: parsed.body.trim(),
        bodyZh: typeof parsed.body_zh === 'string' ? parsed.body_zh.trim() : undefined
      })
    } catch {
      // Bad generated copy should not break the whole desktop app.
    }
  }

  return byPersonality
}

const INTRO_COPY_BY_PERSONALITY = parseIntroCopy(introCopyJsonl)

function isChineseLocale(locale: Locale): boolean {
  return CHINESE_LOCALES.has(locale)
}

function localizeCopy(copy: IntroCopy, locale: Locale): IntroCopy {
  if (isChineseLocale(locale) && copy.bodyZh) {
    return { ...copy, body: copy.bodyZh }
  }

  return copy
}

function neutralCopy(locale: Locale): IntroCopy[] {
  const copies = INTRO_COPY_BY_PERSONALITY.none || INTRO_COPY_BY_PERSONALITY.default || FALLBACK_COPY

  return copies.map(copy => localizeCopy(copy, locale))
}

function fallbackCopyForPersonality(personalityKey: string, locale: Locale): IntroCopy[] {
  if (NEUTRAL_PERSONALITIES.has(personalityKey)) {
    return neutralCopy(locale)
  }

  const label = titleize(personalityKey)

  if (isChineseLocale(locale)) {
    return [
      {
        headline: `${label} 模式已开启。我们要审计什么？`,
        body: '发送建筑数据、账单或改造想法。我会使用你配置的语气，并立足于真实指标进行分析。'
      },
      {
        headline: `${label} 模式的智能审需要看什么？`,
        body: '带上上下文或卡住的地方。我会适应你配置的个性。'
      },
      {
        headline: `${label} 模式已就绪。`,
        body: '发送问题、数据集或想法。我会遵循你配置的个性。'
      },
      {
        headline: `${label} 模式的智能审要处理什么？`,
        body: '把任务丢过来。我会让分析立足于建筑。'
      },
      {
        headline: '我们应该从哪里开始？',
        body: `给我上下文，我会以 ${label} 模式回复。`
      }
    ]
  }

  return [
    {
      headline: `${label} mode is on. What should we audit?`,
      body: "Send the building data, bill, or retrofit idea. I'll use your configured voice and keep the analysis grounded in real metrics."
    },
    {
      headline: `What does ${label} DechnicAuditor need to see?`,
      body: "Bring the context or the stuck part. I'll adapt to your configured personality."
    },
    {
      headline: `${label} mode is ready.`,
      body: "Send the problem, dataset, or idea. I'll follow the personality you've configured."
    },
    {
      headline: `What should ${label} DechnicAuditor tackle?`,
      body: "Drop the task here. I'll keep the analysis grounded in the building."
    },
    {
      headline: 'Where should we begin?',
      body: `Give me the context and I'll answer in ${label} mode.`
    }
  ]
}

function pickCopy(copies: IntroCopy[], seed = 0): IntroCopy {
  return copies[Math.abs(seed) % copies.length] || FALLBACK_COPY[0]
}

const WORDMARK = '智 能 审'

function resolveCopy(personality: string | undefined, seed: number | undefined, locale: Locale): IntroCopy {
  const personalityKey = normalizeKey(personality)

  const copies = NEUTRAL_PERSONALITIES.has(personalityKey)
    ? INTRO_COPY_BY_PERSONALITY[personalityKey] || neutralCopy(locale)
    : INTRO_COPY_BY_PERSONALITY[personalityKey] || fallbackCopyForPersonality(personalityKey, locale)

  const copy = pickCopy(copies, seed)

  return localizeCopy(copy, locale)
}

export function Intro({ personality, seed }: IntroProps) {
  const { locale } = useI18n()
  const [mountSeed] = useState(() => Math.floor(Math.random() * 100000))
  const copy = resolveCopy(personality, mountSeed + (seed ?? 0), locale)

  return (
    <div
      className="pointer-events-none flex w-full min-w-0 flex-col items-center justify-center px-0.5 py-6 text-center text-muted-foreground sm:px-6 lg:px-8"
      data-slot="aui_intro"
    >
      <div className="w-full min-w-0">
        <p
          aria-label={WORDMARK}
          className="fit-text mx-auto mb-1 w-[calc(100%-1rem)] max-w-[500px] font-['Collapse'] font-bold uppercase leading-[1.25] tracking-[0.08em] mix-blend-plus-lighter py-1"
          style={{
            '--fit-min': '1.5rem',
            color: 'transparent',
            backgroundImage: 'linear-gradient(180deg, #2196F3 0%, #64B5F6 50%, #90CAF9 100%)',
            backgroundClip: 'text',
            WebkitBackgroundClip: 'text',
          } as CSSProperties}
        >
          <span>
            <span>{WORDMARK}</span>
          </span>
          <span aria-hidden="true">{WORDMARK}</span>
        </p>

        <p className="m-0 text-center leading-normal tracking-tight">{copy.body}</p>
      </div>
    </div>
  )
}
