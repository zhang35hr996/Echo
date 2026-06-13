# Echo — 设计稿(MVP)

**日期:** 2026-06-13
**状态:** 已确认,待写实现计划

## 一句话

一个自用的「歌库保险箱 + 场景推荐队列」:后端每天自动盯用户的 YouTube
歌单,防止歌曲悄悄消失;手机上的 PWA 按当前场景给出一条 10–30 首的动态队列,
点一下跳 YouTube Music 播放,每次反馈回喂打分。

**明确不做(MVP):** 内嵌播放器、环境自动识别、Apple Music / 本地源、
LLM 打标签、多用户账号体系。

## 背景与动机

用户在 iPhone 上几乎只用 YouTube Music,基本不听新歌,反复听同一个几百首的
大歌单。两个最痛的点:

1. **找歌累。** 几百首大歌单靠随机或手划找歌,经常一直按「下一首」。希望根据当前
   场景(时间/活动/设备)直接给出大概率想听的队列。
2. **歌会悄悄消失。** YouTube 歌单里的歌有时变私有/被删/下架,用户根本不知道是哪首
   没了,也就无法补回。希望系统自动发现并提示可能的替代版本。

## 关键决策(brainstorm 结论)

| 决策点 | 结论 | 理由 |
|---|---|---|
| 交付形态 | **PWA + Python 后端**(非原生 iOS) | 用户无 Mac,原生 SwiftUI 不现实;PWA 可加主屏、零苹果税、随时迭代,后端以后可被原生 app 复用 |
| MVP 范围 | **P0 快照保险箱 + 推荐队列一起** | 两个最痛的点一次解决 |
| 歌曲来源 | **官方 YouTube Data API v3 + OAuth** | 用户歌单是普通 YouTube 歌单,官方 API 可读且更稳;避免非官方 ytmusicapi |
| 源范围 | **只做 YouTube/YTM**,Apple/本地延后 | registry 表预留 `apple_music_id`/`local_file_path` 字段 |
| 运行时 | **方案 A:免费常驻主机**(Fly.io 免费层或家用树莓派),后端内置 APScheduler 每日定时 | 唯一同时满足「自动 watchdog + 手机随时拿推荐」 |

## 架构总览

```
┌─────────────────────────┐         ┌──────────────────────────────┐
│  PWA (手机加到主屏)       │  HTTPS  │  FastAPI + SQLite (Fly.io)    │
│  - 4 个场景按钮           │ ──────▶ │  - /queue  /feedback  /alerts │
│  - 动态队列 + 反馈按钮     │ ◀────── │  - APScheduler 每日快照任务    │
│  - 点歌跳 YT Music link   │         │  - 同进程顺手托管 PWA 静态文件  │
│  - 消失歌曲 alert 列表     │         └───────────────┬──────────────┘
└─────────────────────────┘                         │ OAuth
                                          ┌──────────▼───────────┐
                                          │ YouTube Data API v3   │
                                          └───────────────────────┘
```

- **前端 PWA:** 安装到主屏、全屏图标。首页 4 个场景按钮 → 点进去是动态队列页
  (不是静态歌单),每首带反馈按钮。独立的「消失歌曲」alert 列表页用于一键确认替代。
- **后端 FastAPI + SQLite:** 单进程同时承载 API、APScheduler 定时任务、以及托管
  PWA 静态文件。SQLite 单文件做自用库,单写无并发冲突。
- **YouTube 摄取:** YouTube Data API v3,OAuth 读用户自己的歌单。

## 模块拆分

每个模块职责单一、通过明确接口通信、可独立测试。

| 模块 | 职责 | 关键接口 |
|---|---|---|
| `ingest/youtube` | OAuth + 拉歌单条目 | `get_playlist_items(playlist_id) -> [RawItem]` |
| `snapshot` | 存每日快照 + 与上次 diff | `capture(playlist_id)`, `diff(prev, cur) -> Changes` |
| `registry` | canonical 歌曲表、标题归一化、去重、消失歌的替代候选搜索 | `upsert_track()`, `find_replacements(title, artist, duration)` |
| `recommend` | 加权打分 + 生成队列 | `build_queue(scene, seed_track?) -> [Track]` |
| `feedback` | 记录 play_events、聚合 track_context_stats | `record(event)` |
| `api` | FastAPI 路由 | `/queue` `/feedback` `/alerts` `/resolve` |
| `scheduler` | 每天触发 snapshot→diff→watchdog | APScheduler cron |
| `web` | PWA(manifest + service worker + 4 按钮 + 队列页) | — |

## 数据流

1. **每日(自动):** scheduler → `ingest` 拉歌单 → `snapshot` 存当天全量 →
   `diff` 上一版 → 消失的标 `missing` → `registry` 用 标题+歌手+时长 搜替代候选 →
   结果进 `/alerts`。
2. **听歌(手动):** 开 PWA → 点场景按钮 →(可选先点一首当 session seed)→
   `recommend` 用打分公式从 registry+stats 出队列 → 点歌跳 YT Music →
   点反馈(听完了/不想听/太吵/正中)→ `feedback` 记事件 + 更新 stats。

## 推荐打分(无 ML)

```
score = base_like_score
      + scene_match + time_match
      + manual_pick_bonus + completion_bonus + rediscovery_bonus
      - recent_overplay_penalty - skip_penalty
```

- session seed 一旦存在,其情绪/节奏/熟悉度权重高于场景信号。
- 首页 4 个场景按钮:`现在想听` / `最近没听但大概率喜欢` / `低刺激循环` /
  `高能(开车/走路)`。每个映射到一组 scene tag。
- 反馈语义:`manual_pick`=强正、`listened_full`=正、`repeat`=强正、
  `skip_fast`=负、`too_noisy`=当前场景负、`tired_of_it`=短期降权。

## 数据表

沿用以下结构(`tracks` 预留 `apple_music_id` / `local_file_path` 空字段):

- `tracks` — id, title, artist, album, duration_seconds, youtube_video_id,
  apple_music_id, local_asset_id, status, created_at, updated_at
- `track_tags` — track_id, tag_type(mood/scene/energy), tag_value, confidence,
  source(manual/inferred/llm)
- `playlist_snapshots` — id, source, playlist_id, captured_at
- `playlist_snapshot_items` — snapshot_id, source_track_id, title_at_time,
  artist_at_time, position, available
- `play_events` — id, track_id, played_at, scene, action(play/skip/replay/
  finish/manual_pick), source, listened_seconds
- `recommendation_events` — id, scene, generated_at, candidate_track_id, rank,
  score, accepted
- `track_context_stats` — track_id, context_key, play_count, skip_count,
  manual_pick_count, avg_completion, last_played_at

标签 MVP 先手动 + 简单启发式;LLM 打标签延后。

## 错误处理

- OAuth token 自动 refresh。
- 拉取失败 → 保留上一份快照、标记本次任务失败、进 alert。**绝不因抓取失败误判歌
  消失**(消失判定只在成功抓到完整新快照后才与上一版对比)。
- 替代候选搜不到 → 标 `unresolved`,用户以后手动解决,不阻塞流程。
- SQLite 单写:scheduler 与 API 同进程,无并发写冲突。
- 自用单人:私有主机上用一个简单共享 token 做访问保护,不做完整账号体系。

## 测试

pytest。重点单测:

- `diff` 引擎 —— 用 fixture 快照对比(新增/消失/改名/换位)。
- 打分函数 —— 合成 stats 验证排序。
- 标题归一化 / 去重。
- YouTube API 用 mock,不打真实网络。

核心逻辑(diff、打分、归一化)覆盖 80%+。

## 明确不做(YAGNI)

内嵌播放器、环境自动识别(只手动按钮)、Apple Music / 本地源、LLM 打标签、
多用户账号体系。这些字段/接口预留,但本期不实现。
