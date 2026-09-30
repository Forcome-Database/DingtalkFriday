# 钉钉接口请求数量优化：官方文档核验

调查日期：2026-09-30。范围：保留当前请假类型、时长、撤销准确性，出差/外出每日明细、半天/小时、未来行程、月度/年度导出和历史补偿。本文件记录调查阶段的官方文档/官方 SDK 接口事实及方案边界，另以“运行态补证”明确标识后续实测发现；不保存个人数据或凭证。后续修复已经部署，最终实现与验收见 [实施与验证记录](2026-09-30-implementation-and-verification.md)。这里的建议和旧请求模型不能替代修复后的状态判断。

## 主要结论

1. **可以直接扩大假期流水分页**：现用 `/topapi/attendance/vacation/record/list` 的 `size` 官方最大值是 **200**，不是 50；人员上限仍为 50。每个假期类型/人员批次从 `ceil(R/50)` 页变成 `ceil(R/200)` 页，分页密集时该部分请求最多约减少 75%。新版相同人员/分页上限，迁移新版本身不会减少请求。[S2][S3]
2. **减少出差/外出请求的主方向是审批事件 + 本地审批缓存 + 定点日明细校验**。官方支持企业内部应用通过 Stream 或 HTTP 收到 `bpms_instance_change`，可按审批模板订阅。新增或变更审批才补取详情、刷新其影响日期，日常不必逐人逐日扫描全部空日期。但审批表单总时长不能自行等同于每日考勤时长，必须先建立与现有日数据的一致性证据；历史初始化、事件遗漏补偿仍须保留。[S6][S7][S10]
3. **未证实 `/topapi/attendance/getapprovalinfo` 是当前可用的等价批量接口**。2026-09-30 官方当前服务端 API 目录无此接口，官方旧版 Java SDK 下载包的 2025-07-17 源码 JAR 无 `OapiAttendanceGetapprovalinfoRequest/Response`，有 `OapiAttendanceGetupdatedataRequest/Response`。这不足以证明接口绝不存在，但不能将其纳入已证实方案。[S16][S17]
4. **官方报表接口不是“100 人一次跨日期”的替代接口**。`getcolumnval` 能按单人获取最多 31 天的每日 `date/value`，但假期列没有列 ID；假期报表 `getleavetimebynames` 也是单人，且不能查询 225 天以前数据。均未承诺未来审批、撤销明细或完整年度历史，因此不能全量替代当前功能。[S8][S9]

## 核验方式与文档时效

直接读取钉钉官网目前提供的 `.md` 文档，以及官网前端实际读取的官方静态 HTML。当前服务端 API 目录可通过官网只读 `/api/docCenter/getDocInfoList?tabCode=4a8AMF6u2A` 读取；事件订阅目录 `tabCode=LFcRvVD08N`。官方文档的 `gmtModify` 不代表线上 API 的发布时间，也不能证明接口所有行为都在该日重新核验。

| 文档 | 官方 HTML 中的 `gmtModify` |
| --- | --- |
| 查询请假状态 | 2026-05-27 17:06:25 |
| 旧版批量查询员工假期余额变更记录 | 2026-08-25 09:38:04 |
| 新版批量查询员工假期余额变更记录 | 2025-09-11 21:02:21 |
| 获取用户考勤数据 | 2026-06-23 10:39:15 |
| 获取审批实例 ID 列表 | 2026-04-24 14:10:44 |
| 考勤日报生成：按天统计与多维度数据分析 | 2026-09-23 12:04:30 |

初次官方文档核验未调用本项目真实钉钉业务 API；下文“运行态补证”另注明后续实际查询结果。`firecrawl` CLI 未安装，`npx firecrawl --version` 无可执行入口，改为直接读取上述官网内容；原始下载位于系统临时目录，不入仓库。

## 当前接口上限与优化空间

| 接口 | 官方已证实限制/字段 | 对减少请求的意义 |
| --- | --- | --- |
| `/gettoken` | 有效期 7200 秒；官方要求按应用缓存；有效期内重复获取返回相同结果且自动续期 | 进程/实例共用缓存与并发刷新合并可减少重复请求；不能每次业务请求获取。[S1] |
| `/topapi/v2/department/get` | 单部门 ID | 只有需完整详情时才额外获取。[S4] |
| `/topapi/v2/department/listsub` | 仅下一级；返回 `dept_id/name/parent_id` | 如果项目仅需三个基础字段，列表已能提供，不应为每个节点再次取详情。整个层级仍需遍历。[S4] |
| `/topapi/user/listsimple` | 当前部门；仅 `userid/name`；`size` 最大 100；有 `has_more/next_cursor` | 100 已到上限；不能假设一次含所有子部门成员。[S5] |
| `/topapi/attendance/getleavestatus` | 最多 100 人；时间区间最多 180 天；`size` 最大 20；`has_more` | 现有批次/分页已经到上限；不要删除它来换取较少请求而丢失权威每日时长。[S2a] |
| `/topapi/attendance/vacation/type/list` | `vacation_source=all` 获取所有类型；返回名称、单位等 | 可缓存类型元数据，但变更后须刷新；不要只取通过接口新增的类型。[S2b] |
| `/topapi/attendance/vacation/record/list` | 必须指定假期类型；最多 50 人；`size` 最大 200；无开始/结束或修改时间过滤参数 | 50 -> 200 是确定收益；本地日期过滤不会让钉钉少返回历史页。[S2] |
| `/v1.0/attendance/vacations/records/query` | 最多 50 人；`pageSize` 最大 200；无日期过滤；返回 `gmtCreate/gmtModified` | 可辅助本地冲突追踪，但无“修改时间增量游标”或保证排序，不能看到旧记录就提前停止分页。[S3] |
| `/topapi/attendance/getupdatedata` | 单 `userid`、单 `work_date` | 无已证实人员/日期批量参数，是最需通过事件与缓存减少全扫描的接口。[S6] |

注意：新版假期流水 `pageNumber` 的参数描述为首次 0、后续累计偏移量，但官方示例使用 1；旧版描述又称 `offset` 为页码。实际分页语义需按现有已经验证的行为确定，不能仅改 page size 后自行改变 cursor 递增规则。[S2][S3]

## 请假状态、类型与撤销

官方 `getleavestatus` 明确返回“指定时间段内每天的请假状态和请假时长信息”，其中 `duration_percent` 是实际时长乘 100，单位 `percent_day/percent_hour`。其响应示例含 `leave_code`，但响应字段表未列出该字段，因此不宜将其作为所有响应都一定具备的保证。[S2a]

假期流水同时包含余额修改与请假消费，必须区分 `leave_record_type`、`cal_type` 和 `leave_status`。官方旧版/新版的状态定义相同：[S2][S3]

| 字段值 | 官方定义 |
| --- | --- |
| `init` | 请假申请中 |
| `success` | 请假并已通过 |
| `refuse` | 请假但被拒绝 |
| `abort` | 请假撤销 |
| `revoke` | 请假已通过，但是撤销请假并已同意 |
| `cal_type=null` 或字段缺省 | 请假消耗 |

官方没有将 `init` 描述为后台计算任务状态，也没有承诺状态接口和流水接口强一致或给出延迟上限。因此，当状态接口有有效日记录而流水状态仍为 `init` 或暂未匹配时，应保留并显式记录冲突，定点回查确认类型/状态；仅取两接口交集会把暂时不一致转换成实际漏记。这里是工程推导，需企业样本验证，不能凭官方字段说明认定哪个具体冲突已经解决。

## 出差与外出的日明细不能直接用审批总量替代

`getupdatedata.approve_list` 官方字段：[S6]

| 字段 | 官方含义 |
| --- | --- |
| `duration_unit` | 审批单的单位，示例 `day` |
| `duration` | 时长，示例 `2.0` |
| `sub_type` | 子类型名称，例如年假 |
| `tag_name` | 审批类型名称：请假、出差、外出、加班 |
| `biz_type` | **1=加班，2=出差/外出，3=请假** |
| `procInst_id` | 审批单 ID |
| `begin_time/end_time` | 审批单开始/结束时间 |
| `gmt_finished` | 审批完成时间 |

文档只写“时长”，没有说明它是某 `work_date` 当天时长还是完整审批总时长；没有撤销标记，也没有明确保证只返回当前仍有效的审批。不能仅凭它处在单日查询响应中就断定 `duration` 是每天的值，亦不能断定总量应每天复用。需要用短时外出、跨日、午休、半天、小时、非标准班次等样本确认。

审批实例详情返回表单 `value/extValue/componentType`、状态、操作记录、业务动作和附属实例，但官方契约没有直接给出与考勤日统计等价的逐日时长。仅按日历拆分开始/结束时间不能保证与考勤排班、午休等规则一致。[S7]

### 运行态补证：旧日期查询限制

2026-09-30 实际查询 `work_date=2025-11-23` 时，`getupdatedata` 返回 `850002: 禁止查询半年以前的数据`。重新核对当前 [S6] 接口页与 [S20] 全局错误码页，均未查到半年限制或 `850002`。这是本企业本次运行时观察到的限制，不是已写入官方文档的历史下界承诺；“半年”也不能自行换算成 180 天。该结果不能通过重复相同查询恢复，旧日期补采应明确呈现缺口。

已知审批 ID 的 Workflow 详情可作为旧数据修复候选：旧版 `form_component_values` 的 `value/ext_value`、新版 `formComponentValues` 的对应字段可能包含总时长和单位。修复时还须核对 `status/result`，并遍历附属实例的 MODIFY/REVOKE 动作。后续实测还发现同一审批 ID 可以含多个合法行程区间，必须按原 `begin_time/end_time` 核验各段，不能把整份表单总量重复套到每段。官方未承诺这些表单值与每日考勤时长分配等价，必须先用半年内可取得考勤日数据的样本交叉验证，才可用于旧日期；不能仅凭获得表单总时长就宣称历史已正确恢复。[S7][S7b]

`getcolumnval` 当前文档未注明历史查询下界，可按企业列定义进行条件性测试，尚未证明能恢复这些旧出差日值。`getleavetimebynames` 是假期报表且不能获取 225 天前数据，不能作为旧出差恢复方案。[S8][S9]

## 审批实例 API 与历史补偿

已证实的实例列表接口是 **`POST /v1.0/workflow/processes/instanceIds/query`**，不是本次尚未证实的 `/v1.0/workflow/processInstances/query`。[S7a]

| 能力 | 已证实限制 |
| --- | --- |
| 列表 | 必填 `processCode`，按审批发起时间查询；`maxResults` 最大 20；`userIds` 可省略，若传入最多 10；`statuses` 可省略得到所有状态 |
| 时间 | 同时传 start/end 时区间不超过 120 天，普通客户 start 距当前不超过 365 天；OA 高级版历史最长 5 年；仅传 start 时距今不超过 120 天 |
| 总量 | 循环批量 ID 数最多 10000；需要按时间进一步分割超过上限的范围 |
| 详情 | `GET /v1.0/workflow/processInstances?processInstanceId=...`，逐实例详情，无已证实批量详情 |

列表按**发起时间**，不是出差/请假生效时间，也不是最后修改时间。已知实例可缓存；未来行程来自已经发起审批的表单未来开始/结束时间，而不是将列表查询时间直接设置为未来日期。补偿扫描最近发起时间不能发现很久以前发起而今天修改/撤销的旧实例，需事件、已知未结束/可变实例的定期复核与历史校验共同覆盖。

详情 `status=COMPLETED` 且 `result=agree` 表示审批完成通过；`TERMINATED` 为撤销。旧版详情文档还明确：**已通过实例被修改/撤销，会生成附属实例，需要遍历 `attached_process_instance_ids` 并查询其 `biz_action`**。新版有对应 `attachedProcessInstanceIds/bizAction`。仅检查原审批状态会漏掉已通过后的修改/撤销。[S7][S7b]

## 事件订阅、Stream 与 HTTP

企业内部应用可订阅 `bpms_instance_change`，官方明确支持 **Stream 与 HTTP**，不支持 SyncHTTP/RDS。事件覆盖实例开始、结束、终止、删除；可按 `processCode`，或 `bizCategoryId + processCode` 与 `type` 选择。事件示例含 `processInstanceId/processCode/staffId/type/result/createTime/finishTime`，不含完整业务表单，因此通常需补取一次实例详情。[S10]

官方常用套件业务分类含 `attendance.goout`（外出）和 `alitrip.business`（出差），但明确要求以具体企业实际分类标识为准。请假未在其常用分类表中明确列出，须获取企业具体模板/分类标识。[S10]

注意不要误用 `workflow_instance_change_broadcast`：该广播事件官方说明为第三方企业应用授权场景，**不支持企业内部应用**；本项目企业内部应用应核验并使用 `bpms_instance_change`。[S11]

`attend_bossCheck_change` 官方总述说明为**管理员修改考勤结果**，携带 `userId/workDate/planId`，可用于刷新特定员工/日期；不能把它当成所有请假、出差审批变化的完整事件来源。旧考勤事件含打卡、排班、加班、组、班次变化，并没有承诺全部审批变化由此发送。[S12][S13]

通讯录用户更改 `user_modify_org` 和部门创建/修改/删除、用户离职等企业内部应用事件支持 Stream 与 HTTP。用户更改事件明确不覆盖个人头像、昵称、钉钉号等个人信息变化；用事件更新通讯录后仍需要周期性校验，不能将所有个人字段认定为实时同步。[S14]

Stream 是官方推荐方式，通过 WebSocket，无需公网回调地址和注册回调加密密钥。官方 SDK 示例有 `eventId` 和成功/稍后处理的 ACK，可实现持久化 inbox、去重与失败重试。Stream 是事件传输渠道，不是审批历史查询或历史补发 API；本次读取的文档未明确承诺重放保留时长、严格有序、exactly-once 或无限重试。补偿查询和事件去重必须保留，不能据此保证“零轮询且永不漏数据”。HTTP 回调需加解密并及时返回，官方验证说明要求在 1500ms 内响应。[S15][S15a][S18]

后续实施已运行事件 inbox 持久化、ACK、实例详情与日期刷新链，但尚未完成真实钉钉变更自动投递验证。连接成功、模拟事件与诊断事件仅能证明各自覆盖的链路，最终运行态证据见 [实施与验证记录](2026-09-30-implementation-and-verification.md)。

## 报表 API 的条件性替代

`getattcolumns` 要求已启用智能统计；获取假期字段不返回 ID，官方要求改用 `getleavetimebynames`。[S8a]

`getcolumnval` 请求为单 `userid`、最多 20 列、最多 31 天；返回按天的 `date/value`。与逐日 `getupdatedata` 相比，它可能把单人一个月的“每日指标值”压到一个请求。但它不支持离职人员，不返回审批 ID/起止/撤销状态，文档没有承诺出差/外出列总是存在或单位是什么，也没有承诺未来审批日值。只有企业列定义和对照数据证明正确后，才能替代相应历史日时长采集；审批/未来/撤销能力仍需其他来源。[S8]

`getleavetimebynames` 为单人、最多 20 个假期名称、区间最多 31 天、不能获取 225 天前数据；无法等价保留年度历史补偿。官方 2026-09-23 日报方案仍引用 `getattcolumns/getcolumnval` 并明确按天值由本地汇总，没有提供 100 人跨日期的新版替代契约。[S9][S9a]

企业级 `/v1.0/datacenter/attendanceData` 返回企业指标汇总而不是员工审批明细，且官方 2023-09-01 已关闭新增权限入口；不能当作当前可直接接入、保留人员明细的替代方案。[S19]

## 建议验收与推进顺序

1. 扩大假期流水 `size=200`，验证 `has_more`、分页终止、重复/遗漏、请假/撤销与旧流程结果一致。
2. 缓存稳定元数据、合并并发同参数请求；通讯录先形成完整当前快照，再按事件更新，定期校验。不要为了降低请求而永久保留已删除部门。
3. 建审批实例缓存与事件 inbox；处理 start/finish/terminate/delete 及附属修改/撤销，按员工和影响日期合并待刷新任务。
4. 用真实覆盖样本对照审批与 `getupdatedata`/报表 daily 时长，明确哪些字段能等价重建，哪些日期必须定点校验；尚未证明正确的内容继续走现有采集。
5. 为事件断连、投递失败、跨接口暂不一致保留定点重试和历史补偿。事件正常时降低扫描频率，按缺口扩大补偿范围；不能只对“最近发起”实例扫描就认定所有历史变更已覆盖。

上述第 1 项是官方契约直接支持的数量优化；其余为设计建议，实际收益取决于员工数、审批频率、活跃日期、已有缓存和订阅覆盖，不以未经测量的全项目固定降幅承诺。

## 官方来源

- [S1 获取企业内部应用 access_token](https://open.dingtalk.com/document/development/obtain-orgapp-token.md)
- [S2 旧版批量查询员工假期余额变更记录](https://open.dingtalk.com/document/development/query-holiday-consumption-records.md)
- [S2a 查询请假状态](https://open.dingtalk.com/document/development/query-status.md)
- [S2b 查询假期规则列表](https://open.dingtalk.com/document/development/holiday-type-query.md)
- [S3 新版批量查询员工假期余额变更记录](https://open.dingtalk.com/document/development/batch-query-employee-leave-balance-change-record.md)
- [S4 获取部门列表](https://open.dingtalk.com/document/development/user-management-acquires-the-list-departments.md)，[获取部门详情](https://open.dingtalk.com/document/development/query-department-details0-v2.md)
- [S5 获取部门用户基础信息](https://open.dingtalk.com/document/development/queries-the-simple-information-of-a-department-user.md)
- [S6 获取用户考勤数据](https://open.dingtalk.com/document/development/obtain-the-attendance-update-data.md)
- [S7 新版获取单个审批实例详情](https://open.dingtalk.com/document/development/obtains-the-details-of-a-single-approval-instance-pop.md)
- [S7a 获取审批实例 ID 列表](https://open.dingtalk.com/document/development/obtain-an-approval-list-of-instance-ids.md)
- [S7b 旧版获取单个审批实例详情](https://open.dingtalk.com/document/development/get-details-single-approval-instance.md)
- [S8 获取考勤报表列值](https://open.dingtalk.com/document/development/queries-the-column-value-of-the-attendance-report.md)
- [S8a 获取考勤报表列定义](https://open.dingtalk.com/document/development/queries-the-enterprise-attendance-report-column.md)
- [S9 获取报表假期数据](https://open.dingtalk.com/document/development/obtains-the-holiday-data-from-the-smart-attendance-report.md)
- [S9a 考勤日报生成：按天统计与多维度数据分析](https://open.dingtalk.com/document/development/obtain-the-employee-attendance-report-information.md)
- [S10 审批实例开始、结束、终止、删除](https://open.dingtalk.com/document/development/event-bpms-instance-change.md)
- [S11 审批实例状态变更（广播）](https://open.dingtalk.com/document/development/approve-instance-state-change-event-broadcast-stream.md)
- [S12 考勤结果变更](https://open.dingtalk.com/document/development/change-of-attendance-results.md)
- [S13 考勤事件](https://open.dingtalk.com/document/development/attendance-events.md)
- [S14 通讯录用户更改](https://open.dingtalk.com/document/development/address-book-user-change.md)，[企业部门创建](https://open.dingtalk.com/document/development/create-department-event.md)，[事件订阅总览](https://open.dingtalk.com/document/development/org-event-overview.md)
- [S15 事件订阅概述](https://open.dingtalk.com/document/development/event-subscription-overview.md)，[配置 Stream 推送](https://open.dingtalk.com/document/development/stream.md)
- [S15a HTTP 回调概述](https://open.dingtalk.com/document/development/http-callback-overview.md)
- [S16 官方服务端 API 目录](https://open.dingtalk.com/api/docCenter/getDocInfoList?tabCode=4a8AMF6u2A)
- [S17 服务端 SDK 下载文档](https://open.dingtalk.com/document/development/download-the-server-side-sdk.md)，[官方旧版 Java SDK 下载包](https://open-dev.dingtalk.com/download/openSDK/java)
- [S18 官方 Python Stream SDK](https://github.com/open-dingtalk/dingtalk-stream-sdk-python)
- [S19 获取企业考勤统计数据](https://open.dingtalk.com/document/development/queries-enterprise-attendance-statistics.md)
- [S20 服务端 API 全局错误码](https://open.dingtalk.com/document/development/server-api-error-codes-1.md)
