[简体中文](README.zh-CN.md) | [English](README.md)

# Garmin MCP Server

这个 Model Context Protocol（MCP）服务器连接 Garmin Connect，并将你的健身与健康数据提供给 Claude 和其他兼容 MCP 的客户端。

Garmin API 通过优秀的 [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) 库访问。

## 功能

- 分页列出近期活动
- 获取活动详情
- 编辑活动：名称、类型、描述/备注、赛事类型、主观运动强度（RPE）、感受以及力量训练组数
- 获取健康指标（步数、心率、睡眠、压力、呼吸）
- 查看身体成分数据
- 查看训练状态与训练准备度
- 获取骑行 FTP 和乳酸阈值指标
- 管理装备，包括 `get_gear` 返回的自由文本备注
- 获取训练和训练计划
- 查看详细的训练步骤结构，包括重复组和游泳配速目标
- 按周汇总健康数据（步数、压力、强度分钟数）
- 高级骑行分析：功率区间、FIT 文件分析、DI2 电子变速分析
- 训练负荷趋势（CTL/ATL/TSB）、HRV 趋势、VO₂ max 趋势、呼吸频率趋势
- 功率持续时间曲线、爬升检测与 VAM、有氧解耦（心脏漂移）、W/kg 计算

### 工具覆盖范围

本 MCP 服务器实现了 **110 多个工具**，覆盖 [python-garminconnect](https://github.com/cyberjunky/python-garminconnect)（v0.3.2）约 90% 的功能：

- ✅ 活动管理（21 个工具）——包含活动类型、描述、赛事类型、主观运动强度、感受和力量训练组数的写入工具
- ✅ 健康与身体状况（34 个工具）——包含轻量级自定义汇总工具
- ✅ 训练与表现（13 个工具）——包含 CTL/ATL/TSB、HRV、VO₂ max 和呼吸趋势
- ✅ 训练计划（8 个工具）
- ✅ 设备（8 个工具）——包含向设备发送训练
- ✅ 装备管理（5 个工具）
- ✅ 体重追踪（5 个工具）
- ✅ 挑战与徽章（10 个工具）
- ✅ 营养（9 个工具）——食物日志、餐食、自定义食物、记录摄入以及多日摄入汇总
- ✅ 女性健康（3 个工具）
- ✅ 用户资料（3 个工具）
- ✅ 高级训练创建工具（4 个工具）——无需编写 JSON 即可创建和安排训练
- ✅ 路线（5 个工具）——列出/获取详情、将 GPX 上传为路线、下载 GPX、删除路线
- ✅ 活动分析（2 个工具）——FIT 文件解析、功率持续时间曲线；需要功率计和/或 Di2
- ✅ 活动文件下载（2 个工具）——下载 FIT、GPX、TCX 或 CSV 格式的活动文件

> **注意：** 活动分析工具需要兼容的功率计（如 Garmin Rally、Favero Assioma、PowerTap P1）和/或 Shimano Di2 / SRAM eTap 电子变速系统。`fitparse` 依赖会自动安装。

### 装备备注

`get_gear` 返回的 `gear` 数组中，每件装备都包含 `notes` 字段，对应 Garmin Connect 中显示的自由文本备注。没有备注的装备返回 `null`；其他现有装备字段保持不变。

### 活动文件下载

以下两个工具可将原始活动文件下载到磁盘：

- **`download_activity_file(activity_id, format="fit", output_dir=None)`** ——下载活动并保存到配置的目录。`format` 支持 `fit`（默认）、`gpx`、`tcx` 或 `csv`。
- **`set_fit_download_dir(path)`** ——设置并持久化默认下载目录（写入配置文件）。

**文件保存位置的优先顺序：**

1. `output_dir` 参数——仅对本次下载有效，不会持久化。
2. `GARMIN_FIT_DOWNLOAD_DIR` 环境变量。
3. 通过 `set_fit_download_dir` 保存的配置。

**首次使用时：**如果尚未配置目录，`download_activity_file` 会返回 `status: "needs_setup"`。助手会询问保存位置（默认建议当前目录），调用 `set_fit_download_dir` 保存选择，然后自动重试下载。

### 力量训练组数

`set_activity_exercise_sets(activity_id, sets)` 会将结构化训练组写入已记录的力量训练活动，使用与 Garmin Connect“编辑组数”页面相同的逐组数据格式，因此这些数据会显示在 Garmin 的训练历史和训练量图表中。此操作会**替换所有现有组数**，包括手表自动识别的组数；如需保留现有数据，请先使用 `get_activity_exercise_sets` 读取。

每组需要提供 `category`，并可选提供 `exercise_name`；两者使用 Garmin 在 [`Exercises.json`](https://connect.garmin.com/web-data/exercises/Exercises.json) 中定义的键。还可选提供 `reps`、`weight_kg` 或 `weight_lb`（自重训练时省略）、`duration_seconds` 和 `rest_seconds`。Garmin 会拒绝未知键，并保持活动不变。

如果手表正确记录了组数，但识别错了动作，可以传入 `keep_timing: true`：保留记录的开始时间、持续时间和休息时间，仅按顺序替换动作、次数和重量。组数必须与活动中记录的有效训练组数相同。

```json
{
  "activity_id": 12345678901,
  "sets": [
    {"category": "DEADLIFT", "exercise_name": "BARBELL_DEADLIFT", "reps": 5, "weight_kg": 150, "rest_seconds": 180},
    {"category": "PULL_UP", "reps": 8}
  ]
}
```

### 有意未实现的接口

出于性能或复杂度考虑，部分接口没有实现：

**数据量较大的接口：**
- `get_activity_details()` ——返回大量 GPS 轨迹和图表数据（50KB–500KB）。如需活动摘要，请改用 `get_activity()`。

**专用训练格式：**
- `upload_running_workout()`、`upload_cycling_workout()`、`upload_swimming_workout()` ——用于特定运动类型的训练上传。如需通用训练，请使用 `upload_workout()`。

**维护及破坏性操作：**
- `delete_blood_pressure()` ——删除操作需要谨慎处理，因此未实现。
- `delete_activity()` 已实现确认保护：先调用一次预览，再传入 `confirm=true` 调用一次以删除。删除记录会写入 stderr，且无法撤销。
- 内部/认证方法：`login()`、`resume_login()`、`connectapi()`、`download()` ——由底层库自动处理。

如果需要这些接口，请[提交 issue](https://github.com/Taxuspt/garmin_mcp/issues)。

## 工具筛选

此服务器默认注册 155 个工具，对于每次会话都要处理大量上下文的 LLM 来说可能过多。你可以使用以下三个可选环境变量，仅开放需要的工具：

| 环境变量 | 作用 |
|---|---|
| `GARMIN_TOOL_PROFILE` | 按功能区域选择内置工具子集：`minimal`、`health`、`activities`、`workouts`、`training`、`nutrition` 或 `all`（默认）。可以用逗号组合多个配置，例如 `health,training`。 |
| `GARMIN_ENABLED_TOOLS` | 逗号分隔的**允许列表**——设置后只注册列出的工具。与 profile 同时使用时，这些工具会在 profile 的基础上追加。 |
| `GARMIN_DISABLED_TOOLS` | 逗号分隔的**禁用列表**——跳过列出的工具。如果设置了允许列表，则忽略此项；但如果同时设置了 profile，则会从 profile 中移除对应工具。 |

工具名称不区分大小写。若未设置这些变量，所有工具都会注册（默认行为不变）。未匹配到任何工具的名称会被忽略，并在 stderr 输出警告，便于发现拼写错误。未知的 profile 名称会导致服务器在启动时停止，并列出可用配置。

### 内置配置

| 配置 | 工具数 | 覆盖范围 |
|---|---:|---|
| `minimal` | 20 | 近期活动及分段、每日统计、睡眠、HRV、压力、身体电量、训练准备度与训练状态 |
| `health` | 53 | 所有健康相关工具，以及体重、身体成分、血压、水分摄入、女性健康、体能年龄、HRV 和呼吸趋势 |
| `activities` | 41 | 活动列表、详情、分段和编辑；FIT 分析与功率曲线；装备；路线 |
| `workouts` | 26 | 训练库、上传、安排和删除；高级训练创建工具；日历 |
| `training` | 38 | 训练状态、负荷、训练效果、VO₂ max、FTP、乳酸阈值、耐力与爬坡评分、训练准备度、恢复时间、个人纪录、比赛预测、目标、徽章 |
| `nutrition` | 23 | 食物日志、自定义食物、每日营养设置、水分补充、能量平衡 |

每个配置也会包含身份和单位工具（`get_full_name`、`get_heart_rate_zones`、`get_unit_system`、`get_user_profile`、`get_userprofile_settings`），以便客户端正确标注返回的数据。

示例——同时需要训练指标和训练工具的教练会话：

```json
"env": {
  "GARMIN_TOOL_PROFILE": "training,workouts"
}
```

示例——使用健康配置和近期活动，但排除写入工具：

```json
"env": {
  "GARMIN_TOOL_PROFILE": "health",
  "GARMIN_ENABLED_TOOLS": "get_activities,get_activity",
  "GARMIN_DISABLED_TOOLS": "add_weigh_in,add_weigh_in_with_timestamps,delete_weigh_ins,add_body_composition,add_hydration_data,set_blood_pressure"
}
```

示例——不使用配置，手动指定工具：

```json
"env": {
  "GARMIN_ENABLED_TOOLS": "get_sleep_data,get_stress_summary,get_activities"
}
```

## 高级训练工具

这些训练创建工具让 LLM 无需编写原始 Garmin JSON，即可创建和安排训练。

### `create_walk_run_workout`

创建可选带心率区间目标的跑走间歇训练。

```json
{
  "name": "W3 Mié 2:2",
  "run_seconds": 120,
  "walk_seconds": 120,
  "repeats": 9,
  "warmup_min": 10,
  "cooldown_min": 8,
  "hr_zone": "Z3"
}
```

返回：`{"status": "success", "workout_id": 1234567890, ...}`

### `create_z2_walk_workout`

创建稳定的 Z2 步行训练。

```json
{
  "name": "Z2 Walk 45m",
  "duration_min": 45,
  "hr_min": 110,
  "hr_max": 130
}
```

返回：`{"status": "success", "workout_id": 1234567890, ...}`

### `create_strength_workout`

根据动作列表创建力量训练。每个动作会变成一个基于次数的训练步骤，动作名称会保留在步骤描述中。名称也会作为 `exerciseName` 发送，但 Garmin 只会保留与其内置动作键匹配的名称（例如 `FARMERS_CARRY`）；其他名称会被接受，但保存后为空。

`category` 为可选参数，会直接传递给 Garmin。省略时，请求中完全不包含此键，Garmin 可以接受。若提供，则必须是 Garmin 的动作类别之一；包括 `OTHER` 和 `UNASSIGNED` 在内的其他值都会被拒绝，并返回 `400 - Invalid category`。完整列表见 [`Exercises.json`](https://connect.garmin.com/web-data/exercises/Exercises.json)。

```json
{
  "name": "Full Body A",
  "exercises": [
    {"name": "Sentadillas", "sets": 3, "reps": 12, "rest_seconds": 90},
    {"name": "Flexiones",   "sets": 3, "reps": 15, "rest_seconds": 60},
    {"name": "Peso muerto", "sets": 3, "reps": 10, "rest_seconds": 90},
    {"name": "Farmers Carry 40m", "sets": 3, "reps": 1, "rest_seconds": 90, "category": "CARRY"}
  ]
}
```

返回：`{"status": "success", "workout_id": 1234567890, ...}`

### `schedule_week`

一次调用即可安排多个训练。

```json
{
  "week": [
    {"date": "2026-05-12", "workout_id": 1234567890},
    {"date": "2026-05-14", "workout_id": 1234567891}
  ]
}
```

返回：`{"status": "complete", "scheduled": [...]}`

### 完整流程示例

```text
create_walk_run_workout(name="W3 Mié 2:2", run_seconds=120, walk_seconds=120,
                        repeats=9, warmup_min=10, cooldown_min=8)
  → workout_id = 1560092011

schedule_workout(workout_id=1560092011, date="2026-05-06")
  → OK
```

同步手表后，训练会显示在 Forerunner 965 日历中。

### 原始 `upload_workout` 的结束条件

使用自定义训练 JSON 调用 `upload_workout` 或 `upload_workouts` 时，`endCondition.conditionTypeId` 与 `endCondition.conditionTypeKey` 必须遵循 Garmin 的标准映射。Garmin 将数字型 `conditionTypeId` 视为权威值；如果 key 与 ID 冲突，Garmin 会保存与该 ID 对应的条件。

例如，心率结束条件不能使用 ID `4`，因为该 ID 对应的是 `calories`，而不是 `heart.rate`：

```json
{
  "endCondition": {
    "conditionTypeId": 4,
    "conditionTypeKey": "heart.rate"
  },
  "endConditionValue": 145
}
```

心率应使用 ID `6`：

```json
{
  "endCondition": {
    "conditionTypeId": 6,
    "conditionTypeKey": "heart.rate"
  },
  "endConditionValue": 145
}
```

如果使用心率区间作为结束条件，请在同一个 `endCondition` 对象中设置 `endConditionZone`（1–5），并省略 `endConditionValue`。如果两者都提供，Garmin 会保留区间并丢弃数值（已于 2026-09-01 根据生产 API 验证）：

```json
{
  "endCondition": {
    "conditionTypeId": 6,
    "conditionTypeKey": "heart.rate",
    "endConditionZone": 2
  }
}
```

常见结束条件 ID：

| ID | 键 |
|---:|---|
| 1 | `lap.button` |
| 2 | `time` |
| 3 | `distance` |
| 4 | `calories` |
| 5 | `power` |
| 6 | `heart.rate` |
| 7 | `iterations` |
| 8 | `fixed.rest` |
| 9 | `fixed.repetition` |
| 10 | `reps` |
| 11 | `training.peaks.tss` |

### 原始 `upload_workout` 的目标类型

编写 Garmin 原始训练 JSON 时，`targetType.workoutTargetTypeId` 与 `targetType.workoutTargetTypeKey` 必须使用 Garmin 的标准映射。Garmin 以数字 ID 为准：例如 `{"workoutTargetTypeId": 6, "workoutTargetTypeKey": "heart.rate"}` 这样的不匹配请求会被保存为 `pace.zone`，因为 ID `6` 表示 `pace.zone`。

自定义心率范围应使用目标类型 ID `4` 和 `heart.rate.zone`，并将每分钟心跳范围放在 `targetValueOne` / `targetValueTwo` 中。这两个值属于训练步骤，和 `targetType` 同级；不要将它们嵌套在 `targetType` 对象中：

```json
{
  "targetType": {
    "workoutTargetTypeId": 4,
    "workoutTargetTypeKey": "heart.rate.zone"
  },
  "targetValueOne": 143,
  "targetValueTwo": 157
}
```

自定义跑步配速范围也使用相同结构。配速上下限的单位是米/秒：

```json
{
  "targetType": {
    "workoutTargetTypeId": 6,
    "workoutTargetTypeKey": "pace.zone"
  },
  "targetValueOne": 1.9607843,
  "targetValueTwo": 2.0833333
}
```

该示例表示 `8:00–8:30 min/km`。为与心率示例保持一致，较小的数值放在前面；Garmin 会自动规范任意顺序的上下限。Garmin 会静默丢弃嵌套在 `targetType` 中的值，导致配速目标没有生效的范围。上传工具会修复这种明确的错误嵌套；如果嵌套值与步骤级值冲突，则会拒绝请求。

对于 Garmin 命名心率区间，请使用相同目标类型并指定 `zoneNumber`：

```json
{
  "targetType": {
    "workoutTargetTypeId": 4,
    "workoutTargetTypeKey": "heart.rate.zone"
  },
  "zoneNumber": 3
}
```

每个目标只能使用 `zoneNumber` 或 `targetValueOne` / `targetValueTwo` 其中一种。Garmin 将命名区间视为权威值，并静默丢弃同时提供的自定义范围，因此上传工具会拒绝这种含糊的结构。

## 一键安装（Claude Desktop）

最简单的安装方式是使用 `.dxt` Desktop Extension 文件，无需手动编辑 JSON。

### 下载并安装

1. 从[上游 Releases 页面](https://github.com/Taxuspt/garmin_mcp/releases)下载最新的 `garmin-mcp.dxt`。fork 仓库若尚未发布自己的扩展包，请在本地构建，或使用下方通过 GitHub 安装的方式。
2. 将 `.dxt` 文件拖入 Claude Desktop 窗口、双击文件，或打开 **Settings → Extensions → Install Extension** 并选择该文件。
3. Claude Desktop 会提示你填写可选配置（token 路径、邮箱、密码）。

### 首次认证

扩展会自动安装并运行服务器，但首次读取数据前，需要先完成一次 Garmin 认证：

```bash
uvx --python 3.12 --from git+https://github.com/cwwcn/garmin_mcp garmin-mcp-auth
```

OAuth token 会保存到 `~/.garminconnect`。之后服务器可以使用已保存的 token，无需在配置中填写凭据。

> **注意：** token 有效期约为 6 个月。过期后重新运行 `garmin-mcp-auth`。

### 自行构建 `.dxt`

```bash
bash scripts/build_dxt.sh   # 在仓库根目录生成 garmin-mcp.dxt
```

---

## 安装与配置

### MCP 客户端快速开始

将服务器添加到 Claude Desktop、[Codex](https://openai.com/codex/) 或其他 MCP 客户端前，建议先完成一次认证。

#### 前置条件

- Python 3.12 或更高版本
- Garmin Connect 账户
- 如果账户启用了 MFA，登录时可能需要多因素认证

#### 第 1 步：预先认证（仅需一次）

将服务器添加到 MCP 客户端前，在终端中完成一次认证：

```bash
# 安装并运行认证工具
uvx --python 3.12 --from git+https://github.com/cwwcn/garmin_mcp garmin-mcp-auth

# 按提示输入：
# - 邮箱（或设置 GARMIN_EMAIL 环境变量）
# - 密码（或设置 GARMIN_PASSWORD 环境变量）
# - MFA 验证码（如果账户启用了 MFA）

# OAuth token 将保存到 ~/.garminconnect
```

随时可以验证凭据：

```bash
uv run garmin-mcp-auth --verify
```

**注意：**也可以通过环境变量提供凭据：

```bash
GARMIN_EMAIL=your@email.com GARMIN_PASSWORD=secret garmin-mcp-auth
```

如果没有启用 MFA，并且 MCP 客户端支持环境变量，也可以跳过 `garmin-mcp-auth`，直接向客户端提供 `GARMIN_EMAIL` 和 `GARMIN_PASSWORD`。出于安全考虑，建议采用预先认证流程，避免将账号密码写入 MCP 客户端配置。

#### 第 2 步：配置 Claude Desktop

在 Claude Desktop 的 MCP 设置中添加以下配置，**不要填写账号密码**：

- **macOS：** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows：** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "garmin": {
      "command": "uvx",
      "args": [
        "--python",
        "3.12",
        "--from",
        "git+https://github.com/cwwcn/garmin_mcp",
        "garmin-mcp"
      ]
    }
  }
}
```

**重要：**配置中不需要 `GARMIN_EMAIL` 或 `GARMIN_PASSWORD`，服务器会使用此前保存的 token。

#### 第 3 步：重启 MCP 客户端

随后就可以在 MCP 客户端中使用 Garmin 数据。

Codex 和其他客户端的配置示例见下文。

### 同时使用多个 Garmin 账户

单个服务器进程只绑定一个 Garmin 账户。若要同时使用多个账户，需要为每个账户运行一个独立服务器实例，并通过 `GARMINTOKENS` 环境变量为其指定独立的 token 目录。

`GARMINTOKENS` 默认值为 `~/.garminconnect`。将其指向其他目录后，服务器会从该目录读取和写入 token，不会改动默认目录。

#### 第 1 步：分别认证到不同目录

```bash
garmin-mcp-auth --token-path ~/.garminconnect-alice
garmin-mcp-auth --token-path ~/.garminconnect-bob
```

`--token-path` 也接受 `$GARMINTOKENS` 指定的路径，因此设置 `GARMINTOKENS=~/.garminconnect-alice` 后运行 `garmin-mcp-auth`，效果相同。

#### 第 2 步：为每个账户声明一个服务器

```json
{
  "mcpServers": {
    "garmin-alice": {
      "command": "uvx",
      "args": ["--python", "3.12", "--from", "git+https://github.com/cwwcn/garmin_mcp", "garmin-mcp"],
      "env": {
        "GARMINTOKENS": "${HOME}/.garminconnect-alice"
      }
    },
    "garmin-bob": {
      "command": "uvx",
      "args": ["--python", "3.12", "--from", "git+https://github.com/cwwcn/garmin_mcp", "garmin-mcp"],
      "env": {
        "GARMINTOKENS": "${HOME}/.garminconnect-bob"
      }
    }
  }
}
```

服务器启动时会记录它使用的认证目录，方便检查配置是否正确：

```text
Trying to login to Garmin Connect using token data from directory '/home/you/.garminconnect-alice'...
```

#### 注意事项

- **不会静默回退。**如果 `GARMINTOKENS` 指向的目录没有有效 token 且登录失败，服务器会记录错误，工具调用也会失败；HTTP `/readyz` 会保持不可用并返回 503。服务器不会改用默认 token 目录，因此第二个服务器配置错误时，不会悄悄复用第一个账户的会话。
- 即使 MCP 客户端未展开变量，服务器也会展开 `${HOME}`；Windows 下的 `~` 会通过 `USERPROFILE` 解析。
- **限制次要账户的写入工具。**`upload_workout`、`schedule_workout` 等工具会写入该服务器绑定的账户。可以结合 `GARMINTOKENS` 与 `GARMIN_ENABLED_TOOLS`（见[工具筛选](#工具筛选)）将账户设为只读：

  ```json
  "env": {
    "GARMINTOKENS": "${HOME}/.garminconnect-bob",
    "GARMIN_ENABLED_TOOLS": "get_activities,get_activities_by_date,get_activity,get_activity_splits"
  }
  ```

- **token 目录包含长期有效的凭据。**目录仅允许所有者访问；不要将它们放在共享目录或同步文件夹中。

### 开发环境配置

1. 在新环境中安装所需依赖：

```bash
uv sync
```

## 运行服务器

### 配置

服务器通过以下环境变量读取 Garmin Connect 凭据和设置：

- `GARMIN_EMAIL`：Garmin Connect 邮箱地址
- `GARMIN_EMAIL_FILE`：包含 Garmin Connect 邮箱地址的文件路径
- `GARMIN_PASSWORD`：Garmin Connect 密码
- `GARMIN_PASSWORD_FILE`：包含 Garmin Connect 密码的文件路径
- `GARMIN_IS_CN`：设为 `true` 时使用 Garmin Connect 中国区（garmin.cn）；默认 `false`
- `GARMIN_FIT_DOWNLOAD_DIR`：活动文件下载的默认目录。设置后，`download_activity_file` 不会再询问首次使用时的保存位置
- `GARMIN_FIT_CONFIG`：下载目录配置文件的路径，默认为 `~/.garminconnect_fit_config.json`

在 Docker 容器等环境中，可以使用文件保存凭据。不能同时设置 `GARMIN_EMAIL` 和 `GARMIN_EMAIL_FILE`；`GARMIN_PASSWORD` 与 `GARMIN_PASSWORD_FILE` 也同样不能同时设置。

### 传输方式

默认情况下，服务器通过 **stdio** 通信，这是 Claude Desktop、MCP Inspector 和大多数本地客户端所使用的方式。若要通过 **HTTP** 提供服务（例如运行在容器或 Kubernetes 中），可通过环境变量设置传输方式：

- `GARMIN_MCP_TRANSPORT`：`stdio`（默认）、`streamable-http` 或 `sse`
- `GARMIN_MCP_HOST`：HTTP 传输的绑定地址（默认 `127.0.0.1`；只有同时设置 `GARMIN_MCP_HTTP_TOKEN` 或置于带认证的反向代理后，才应设为 `0.0.0.0`）
- `GARMIN_MCP_PORT`：HTTP 传输端口（默认 `8000`）
- `GARMIN_MCP_HTTP_TOKEN`：HTTP 传输使用的共享密钥。设置后，所有发往 `/mcp`、`/sse` 和 `/messages/` 的请求都必须携带 `Authorization: Bearer <token>`，否则返回 `401`。`/healthz` 和 `/readyz` 探针不需要密钥。详见[保护 HTTP 端点](#保护-http-端点)。
- `GARMIN_MCP_STATELESS_HTTP`：设为 `true` 后，`streamable-http` 将以无状态模式运行（默认 `false`）。MCP SDK 会在空闲 30 分钟后丢弃有状态会话，因此空闲后首次调用会收到 `404 Session not found`；部分客户端（包括 claude.ai 自定义连接器）会将其报告为工具调用失败，而不会重新初始化并重试。无状态模式没有会话，因此不会过期。此服务器中的工具都不依赖会话状态，不会丢失功能。建议长期运行的远程部署使用此模式。
- `GARMIN_MCP_CALL_TIMEOUT`：调用 Garmin 时每个请求的超时时间（秒），默认 `90`。Garmin API 偶尔会让单个请求无限期挂起；若没有此限制，调用会一直卡住，直到 MCP 客户端超时并将整个服务器判定为无响应。超时后工具会返回明确且可重试的错误。设为 `0` 可禁用超时限制。

```bash
GARMIN_MCP_TRANSPORT=streamable-http garmin-mcp
```

选择 HTTP 传输方式后：

- MCP 客户端连接 `/mcp` 路径，例如 `http://localhost:8000/mcp`。
- **`GET /healthz`**：服务器启动后即返回 `ok`，可用作**存活探针**。
- **`GET /readyz`**：报告 Garmin 登录是否完成，可用作**就绪探针**。登录成功后返回 `200 {"status": "ready"}`；仍在登录时返回 `503` 和 `{"status": "pending"}`；登录失败则返回 `503` 和 `{"status": "failed"}`（重新运行 `garmin-mcp-auth` 并重启服务器）。

#### 保护 HTTP 端点

HTTP 传输会开放 Garmin 账户的完整读写权限，因此服务器默认只绑定本机回环地址。如果需要让其他机器访问，请设置共享密钥，并要求客户端发送 bearer token：

```bash
export GARMIN_MCP_HTTP_TOKEN="$(openssl rand -hex 32)"
GARMIN_MCP_TRANSPORT=streamable-http GARMIN_MCP_HOST=0.0.0.0 garmin-mcp
```

```bash
# 被拒绝：401 {"error": "unauthorized", ...}
curl -i http://localhost:8000/mcp
# 接受请求（随后继续进行 MCP 握手）
curl -i -H "Authorization: Bearer $GARMIN_MCP_HTTP_TOKEN" http://localhost:8000/mcp
```

大多数 MCP 客户端都支持为远程服务器添加自定义请求头（Claude Desktop 和 claude.ai 连接器、MCP Inspector 以及 SDK 客户端均支持）；在客户端中配置相同的 `Authorization: Bearer …` 请求头。密钥比较采用恒定时间算法。`/healthz` 和 `/readyz` 只报告进程状态和 Garmin 登录结果，因此不要求提供密钥。

未设置 token 时服务器仍会启动；但如果 `GARMIN_MCP_HOST` 不是本机回环地址，stderr 会输出账户暴露风险警告。也可以使用带认证功能的反向代理（如 nginx、Traefik、Authelia 等）；内置 token 是适合常见自托管场景的轻量方案。

### Garmin Connect 中国区（garmin.cn）

如果使用 Garmin Connect 中国区（garmin.cn），而不是国际版，请将环境变量 `GARMIN_IS_CN` 设为 `true`：

```bash
# 使用 Garmin Connect 中国区预先认证
GARMIN_IS_CN=true garmin-mcp-auth

# 或使用命令行参数
garmin-mcp-auth --is-cn
```

在 Claude Desktop 中，将 `GARMIN_IS_CN` 加入 `env` 配置：

```json
{
  "mcpServers": {
    "garmin": {
      "command": "uvx",
      "args": [
        "--python",
        "3.12",
        "--from",
        "git+https://github.com/cwwcn/garmin_mcp",
        "garmin-mcp"
      ],
      "env": {
        "GARMIN_IS_CN": "true"
      }
    }
  }
}
```

使用 Docker 时，可在 `.env` 文件中添加 `GARMIN_IS_CN=true`，或取消 `docker-compose.yml` 中对应行的注释。

### 使用 MCP Inspector 在本地测试服务器

Inspector 可通过 npx 直接运行，无需预先安装。从项目根目录执行：

```bash
npx @modelcontextprotocol/inspector uv run garmin-mcp
```

随后即可查看并测试工具。

### Claude Desktop 配置

1. 创建 Claude Desktop 配置：

编辑 Claude Desktop 配置文件：

- macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows：`%APPDATA%\Claude\claude_desktop_config.json`

有两种方式在 Claude 中运行本地 MCP。

#### 直接从 GitHub 安装，无需克隆仓库

1. 添加以下服务器配置：

```json
{
  "mcpServers": {
    "garmin": {
      "command": "uvx",
      "args": [
        "--python",
        "3.12",
        "--from",
        "git+https://github.com/cwwcn/garmin_mcp",
        "garmin-mcp"
      ],
      "env": {
        "GARMIN_EMAIL": "YOUR_GARMIN_EMAIL",
        "GARMIN_PASSWORD": "YOUR_GARMIN_PASSWORD"
      }
    }
  }
}
```

你可能需要填写 `uvx` 的完整路径。可通过 `which uvx` 查看。

2. 重启 Claude Desktop。

#### 从本地仓库运行

1. 添加以下服务器配置：

```json
{
  "mcpServers": {
    "garmin-local": {
      "command": "uv",
      "args": [
        "--directory",
        "<本地仓库的完整路径>/garmin_mcp",
        "run",
        "garmin-mcp"
      ]
    }
  }
}
```

2. 重启 Claude Desktop。

### Codex 配置

Codex 使用 TOML 配置 MCP 服务器。先运行 `garmin-mcp-auth` 完成认证，然后将以下配置之一添加到 `~/.codex/config.toml`。

也可以让支持 MCP 的客户端代为配置。例如：

```text
请从 https://github.com/cwwcn/garmin_mcp 安装 Garmin MCP 服务器，使用 garmin-mcp-auth 完成认证，并将服务器加入 MCP 配置；不要在配置中保存我的 Garmin 邮箱或密码。
```

#### 直接从 GitHub 安装，无需克隆仓库

```toml
[mcp_servers.garmin]
command = "uvx"
args = [
  "--python",
  "3.12",
  "--from",
  "git+https://github.com/cwwcn/garmin_mcp",
  "garmin-mcp"
]
```

#### 从本地仓库运行

```toml
[mcp_servers.garmin-local]
command = "uv"
args = [
  "--directory",
  "/本地路径/garmin_mcp",
  "run",
  "garmin-mcp"
]
```

保存后重启 MCP 客户端。

### opencode 配置

从仓库根目录启动时，[opencode](https://opencode.ai) 会自动加载项目级 `opencode.json`。因此，克隆本仓库的贡献者无需额外配置，就可以将本地源代码连接为 Garmin MCP。

#### 从本仓库克隆运行（推荐用于开发）

仓库自带的 [`opencode.json`](./opencode.json) 会通过 `uv run garmin-mcp` 启动 MCP，因此始终使用当前工作区中的代码。

```bash
git clone https://github.com/cwwcn/garmin_mcp.git
cd garmin_mcp
uv sync                # 安装依赖
garmin-mcp-auth        # 首次登录；若 ~/.garminconnect 已存在可跳过
opencode               # 启动并连接 garmin MCP
```

检查服务器是否已连接：

```bash
opencode mcp list
# ●  ✓ garmin   connected
#       uv run garmin-mcp
```

#### 在其他目录中运行（GitHub 安装）

运行 `garmin-mcp-auth` 后，将服务器添加到全局 opencode 配置 `~/.config/opencode/opencode.json`：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "garmin": {
      "type": "local",
      "command": [
        "uvx",
        "--python",
        "3.12",
        "--from",
        "git+https://github.com/cwwcn/garmin_mcp",
        "garmin-mcp"
      ],
      "enabled": true,
      "timeout": 30000
    }
  }
}
```

保存后重启 opencode。首次运行 `uvx` 时会下载并缓存软件包，因此初次启动可能需要等待几秒。

### Docker 部署

Docker 可以提供隔离且一致的 MCP 服务器运行环境。

#### 使用 Docker Compose 快速启动（推荐）

1. 创建 `.env` 文件并填入凭据：

```bash
echo "GARMIN_EMAIL=your_email@example.com" > .env
echo "GARMIN_PASSWORD=your_password" >> .env
```

2. 启动容器：

```bash
docker compose up -d
```

3. 查看服务器日志：

```bash
docker compose logs -f garmin-mcp
```

#### 直接使用 Docker

```bash
# 构建镜像
docker build -t garmin-mcp .

# 启动容器
docker run -it \
  -e GARMIN_EMAIL="your_email@example.com" \
  -e GARMIN_PASSWORD="your_password" \
  -v garmin-tokens:/root/.garminconnect \
  garmin-mcp
```

#### 使用文件保存密钥（更安全）

为了提高安全性，特别是在生产环境中，建议使用密钥文件，而不是环境变量：

1. 创建密钥目录并写入凭据：

```bash
mkdir -p secrets
echo "your_email@example.com" > secrets/garmin_email.txt
echo "your_password" > secrets/garmin_password.txt
chmod 600 secrets/*.txt
```

2. 编辑 [docker-compose.yml](docker-compose.yml)，取消 secrets 配置部分的注释：

```yaml
services:
  garmin-mcp:
    environment:
      - GARMIN_EMAIL_FILE=/run/secrets/garmin_email
      - GARMIN_PASSWORD_FILE=/run/secrets/garmin_password
    secrets:
      - garmin_email
      - garmin_password

secrets:
  garmin_email:
    file: ./secrets/garmin_email.txt
  garmin_password:
    file: ./secrets/garmin_password.txt
```

3. 启动容器：

```bash
docker compose up -d
```

#### 在 Docker 中处理 MFA

如果 Garmin 账户启用了多因素认证（MFA）：

1. 使用服务的 token volume 运行认证 CLI：

```bash
docker compose run --rm --entrypoint garmin-mcp-auth garmin-mcp
```

2. 按提示输入 MFA 验证码：

```text
Garmin Connect MFA required. Please check your email/phone for the code.
Enter MFA code: 123456
```

3. OAuth token 会保存到 Docker volume（`garmin-tokens`），后续运行无需重新认证。

4. 完成 MFA 设置后，正常启动容器：

```bash
docker compose up -d
```

#### Docker volume 管理

OAuth token 保存在持久化 Docker volume 中，以免每次都重新认证：

```bash
# 列出 volume
docker volume ls

# 查看 token volume
docker volume inspect garmin_mcp_garmin-tokens

# 删除 volume（之后需要重新认证）
docker volume rm garmin_mcp_garmin-tokens
```

#### 通过 Docker 与 Claude Desktop 配合使用

可以配置 Claude Desktop 连接容器中的 MCP 服务器。不过，MCP 服务器通常使用 stdio 通信，因此直接启动进程效果最好。通过 Docker 部署时，建议优先使用[Claude Desktop 配置](#claude-desktop-配置)一节中的 `uvx` 方式。

## 使用示例

连接到 Claude 后，可以提出类似问题：

- “显示我最近的活动。”
- “我昨晚睡得怎么样？”
- “我昨天走了多少步？”
- “显示我最近一次跑步的详情。”
- “分析我上次骑行的功率区间，并与训练区间对比。”
- “显示最近 6 周的 CTL、ATL 和 TSB 趋势。”
- “显示我昨天骑行的功率持续时间曲线，并估算 FTP。”
- “分析我最近一次骑行活动的 FIT 数据——爬坡时的变速质量如何？”
- “显示最近 2 周的 HRV 趋势，并指出可能的恢复问题。”
- “我本赛季最佳 20 分钟功率是多少？是什么时候达到的？”

## 故障排查

### 对有效活动调用 `get_training_effect` 时返回 HTTP 403

即使活动列表工具能够显示活动，Garmin 的活动详情接口（`/activity-service/activity/{id}`）仍可能返回 **403 Forbidden**。`get_training_effect` 现在会回退到活动列表中搜索；近期活动的列表数据仍包含有氧/无氧训练效果。

如果活动早于近期搜索范围，请通过 `get_activities` / `get_activities_by_date` 列出活动后重试，或直接使用列表中返回的字段。

### `get_goals` 没有返回 Garmin Connect 中已有的目标

Garmin 的 goal-service 只会返回在 Connect 当前“目标”界面中创建的目标（例如月度骑行距离/时间目标），前提是请求包含 `Sec-Fetch-Site: same-origin`，且 `start` 使用从 1 开始的页码。若使用 `start=0`，接口会返回空列表。到 python-garminconnect 0.3.16 为止，其 `get_goals()` 没有同时满足这两个条件，因此此处的 `get_goals` 会像 Connect 的“目标”页面一样直接请求 `/goal-service/goal/goals`，并在必要时回退到底层库的调用。

### “Failed to spawn process: No such file or directory”

如果 Claude Desktop 找不到 `uvx`，通常是因为 `uvx` 不在 Claude Desktop 使用的 PATH 中。可以按以下步骤处理：

1. 查找 `uvx` 的安装位置：

```bash
which uvx
```

2. 在配置中填写完整路径。例如 `uvx` 位于 `/Users/username/.cargo/bin/uvx` 时：

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/Users/username/.cargo/bin/uvx",
      "args": [
        "--python",
        "3.12",
        "--from",
        "git+https://github.com/cwwcn/garmin_mcp",
        "garmin-mcp"
      ]
    }
  }
}
```

### Windows：Smart App Control 阻止运行 `uv` / `uvx`

在启用了 **Smart App Control（智能应用控制）** 的 Windows 11 上，启动 Garmin MCP 时，`uv.exe` / `uvx.exe` 可能会被阻止；当 `uv` 尝试从本地 `.venv` 加载未签名的 `garmin-mcp.exe` 时也可能发生。

这与 Microsoft Defender Antivirus 隔离文件不是一回事。Smart App Control 的设置位置是：

**Windows Security → App & browser control → Smart App Control**

#### 现象

- 运行 `uv`、`uvx` 或在 Claude Desktop 中使用 `command: "uvx"` 时收到 Smart App Control 通知
- 虽然已经安装 `uvx`，Claude Desktop 仍无法启动服务器
- Event Viewer → *Applications and Services Logs* → *Microsoft* → *Windows* → *CodeIntegrity* → *Operational* 中出现 **CodeIntegrity Error 3077**，提及 `uv.exe` 和 `garmin-mcp.exe`（策略/企业签名级别）

#### 确认问题

1. 确认 Smart App Control 处于 **On**（Evaluation 或 Enforcement）状态。
2. 在 CodeIntegrity Operational 日志中，查看启动失败时附近的 **3077** 事件。
3. Defender“病毒和威胁防护”历史记录可能为空；这并不能排除 Smart App Control 拦截。

#### 恢复方式（尽量保持 Smart App Control 开启）

1. 通过有打包签名的渠道安装或重新安装 `uv`，然后在 PowerShell 中验证：

   ```powershell
   winget install --id=astral-sh.uv -e
   # 或：scoop install main/uv
   uvx --version
   ```

2. 在 Claude Desktop 中填写 `uvx.exe` 的完整路径（与上文 PATH 故障排查相同），例如：

   ```json
   "command": "C:\\Users\\<you>\\.local\\bin\\uvx.exe"
   ```

3. 如果 Enforcement 仍阻止加载 `garmin-mcp.exe`，可能需要管理员/策略为该二进制文件路径添加例外。全局关闭 Smart App Control 应作为最后手段，不建议默认采用。
4. 如果本地 `uvx` 仍被拦截，可改用 Docker Compose 安装方式。

### 登录问题

如果遇到登录问题：

1. 确认账号凭据正确。
2. 检查 Garmin Connect 是否要求额外验证。
3. 确保 `garminconnect` 软件包为较新版本。

### 日志

如遇其他问题，可查看 Claude Desktop 日志：

- macOS：`~/Library/Logs/Claude/mcp-server-garmin.log`
- Windows：`%APPDATA%\Claude\logs\mcp-server-garmin.log`

### Garmin Connect 多因素认证（MFA）

#### MCP 服务器中的 MFA

MCP 服务器以后台进程运行，无法直接从终端交互。如果 Garmin 账户启用了 MFA，必须先使用预认证工具完成一次认证，之后服务器才能正常运行。

#### 推荐方式：预认证工具

处理 MFA 最简单的方式是使用专用认证工具：

```bash
garmin-mcp-auth
```

OAuth token 会保存到 `~/.garminconnect`，以供后续使用。Claude Desktop 或其他 MCP 客户端启动服务器时会自动使用这些 token。

**其他选项：**

```bash
# 通过环境变量提供凭据
GARMIN_EMAIL=you@example.com GARMIN_PASSWORD=secret garmin-mcp-auth

# 验证已有 token
garmin-mcp-auth --verify

# 查看 token 的查找位置、磁盘文件及可用状态
garmin-mcp-auth --diagnose

# 强制重新认证（例如 token 过期时）
garmin-mcp-auth --force-reauth

# 指定 token 保存位置
garmin-mcp-auth --token-path ~/.garmin_tokens
```

#### 备选方式：手动首次运行

也可以将凭据保存在文件中，并通过认证 CLI 完成认证：

```bash
# 为安全起见，将凭据保存到文件
echo "your_email@example.com" > ~/.garmin_email
echo "your_password" > ~/.garmin_password
chmod 600 ~/.garmin_email ~/.garmin_password

# 启动服务器前运行认证 CLI
GARMIN_EMAIL_FILE=~/.garmin_email GARMIN_PASSWORD_FILE=~/.garmin_password \
  uvx --python 3.12 --from git+https://github.com/cwwcn/garmin_mcp garmin-mcp-auth

# 按提示输入 MFA 验证码
# token 会自动保存
# 然后在 Claude Desktop 配置中添加服务器，无需凭据
```

首次认证后，在 Claude Desktop 中配置服务器时**不要填写账号密码**（token 已保存）：

```json
{
  "mcpServers": {
    "garmin": {
      "command": "uvx",
      "args": [
        "--python",
        "3.12",
        "--from",
        "git+https://github.com/cwwcn/garmin_mcp",
        "garmin-mcp"
      ]
    }
  }
}
```

#### 在 Docker 中使用 MFA

使用 Docker 时，参阅上文[在 Docker 中处理 MFA](#在-docker-中处理-mfa)，该流程能够将 token 持久保存在 volume 中。

#### MFA 故障排查

**错误：`MFA required; run 'garmin-mcp-auth' before starting the server.`**

解决方法：
1. 打开终端。
2. 运行 `garmin-mcp-auth`。
3. 输入账号凭据和 MFA 验证码。
4. 重启 Claude Desktop。

**Token 已过期**

OAuth token 会定期过期（约 6 个月）。重新认证：

```bash
garmin-mcp-auth --force-reauth
```

**验证 token 是否可用**

```bash
garmin-mcp-auth --verify
```

**`garmin-mcp-auth` 成功，但服务器仍无法登录**

服务器只会从 token 目录（`$GARMINTOKENS`，默认 `~/.garminconnect`）中的 `garmin_tokens.json` 读取 token。启动错误会指出实际遇到的问题：目录不存在、token 文件缺失、文件不可读，或 Garmin 拒绝了 token。最常见的原因是 MCP 客户端启动服务器时使用了与运行 `garmin-mcp-auth` 的 shell 不同的 `GARMINTOKENS` 或 `HOME`（Windows 上的 Claude Desktop 中较常见），导致两边解析出的目录不同。可运行以下命令进行核对：

```bash
garmin-mcp-auth --diagnose
```

`garmin-mcp-auth` 还会写入 `~/.garminconnect_base64`，供其他基于 garminconnect 的工具使用；此服务器不会读取该文件。

## 测试

本项目为所有 MCP 工具提供了较完整的测试。**README 中记录的测试状态为全部通过（100%）。**

### 运行测试

```bash
# 运行单元测试和集成测试（默认使用模拟 Garmin API；端到端测试默认不运行）
uv run pytest

# 只运行集成测试
uv run pytest tests/integration/

# 详细模式运行集成测试
uv run pytest tests/integration/ -v

# 运行指定测试模块
uv run pytest tests/integration/test_health_wellness_tools.py -v

# 运行端到端测试（需要真实 Garmin 凭据）
# 部分测试会在账户中创建并删除食物、食物日志和训练
uv run pytest tests/e2e/ -m e2e -v
```

### 测试结构

- **集成测试**（200 多项）：使用 FastMCP 集成和模拟的 Garmin API 响应测试所有 MCP 工具。
- **端到端测试**（`tests/e2e/`）：使用真实 MCP 服务器和 Garmin API 测试，需要有效凭据；仅通过 `-m e2e` 运行。

## 从本地路径重新安装

如果使用本地检出目录或 fork，可通过以下命令强制从本地路径重新安装：

```bash
uv tool install --python 3.12 --force C:\Users\aresd\Desktop\programacion\garmin_mcp
```
