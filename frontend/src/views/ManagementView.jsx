import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Steps,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  BellOutlined,
  CheckCircleOutlined,
  DeploymentUnitOutlined,
  PlusOutlined,
  RadarChartOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { safeArray, statusTag } from "../ui.jsx";

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

function riskTag(level) {
  const normalized = String(level || "medium").toLowerCase();
  const color = normalized === "high" ? "error" : normalized === "low" ? "success" : "warning";
  return <Tag color={color}>{normalized.toUpperCase()}</Tag>;
}

function severityTag(level) {
  const normalized = String(level || "warning").toLowerCase();
  const color = normalized === "critical" ? "error" : normalized === "info" ? "processing" : "warning";
  return <Tag color={color}>{normalized.toUpperCase()}</Tag>;
}

function bandTag(band) {
  const normalized = String(band || "stable").toLowerCase();
  const colorMap = { excellent: "success", stable: "processing", watch: "warning", critical: "error" };
  return <Tag color={colorMap[normalized] || "default"}>{normalized.toUpperCase()}</Tag>;
}

function triggerTypeLabel(type) {
  const map = {
    blocked_task_timeout: "阻塞超时自动升级",
    critical_task_done: "关键任务完成通知",
    agent_offline: "Agent 离线告警",
  };
  return map[type] || type;
}

function channelTypeLabel(type) {
  const map = {
    telegram: "Telegram",
    feishu: "Feishu",
    webhook: "Webhook",
  };
  return map[type] || type;
}

function stageIndex(run) {
  return Math.max(
    0,
    safeArray(run?.stages).findIndex((stage) => stage.key === run?.stageKey),
  );
}

function scoreStroke(score) {
  if (score >= 85) return "#2f7d4b";
  if (score >= 70) return "#2b6ac9";
  if (score >= 55) return "#b8731b";
  return "#b6382f";
}

function ManagementView({
  dashboard,
  permissions,
  agents,
  tasks,
  sessions,
  onCreateRun,
  onUpdateRun,
  onSaveRule,
  onSaveChannel,
  onTestChannel,
  onBootstrapRules,
  onExportReport,
  onSelectTask,
  onOpenConversation,
}) {
  const management = dashboard.management || { summary: {}, runs: [], agentHealth: {}, reports: {}, automation: {} };
  const runs = safeArray(management.runs);
  const ruleData = management.automation || { summary: {}, rules: [], channels: [], alerts: [] };
  const healthData = management.agentHealth || { summary: {}, agents: [] };
  const reportData = management.reports || { daily: [], weekly: {}, bottlenecks: [], relayLeaders: [] };
  const [createOpen, setCreateOpen] = useState(false);
  const [ruleOpen, setRuleOpen] = useState(false);
  const [channelOpen, setChannelOpen] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState(runs[0]?.id || "");
  const [busyAction, setBusyAction] = useState("");
  const [createForm] = Form.useForm();
  const [actionForm] = Form.useForm();
  const [ruleForm] = Form.useForm();
  const [channelForm] = Form.useForm();

  useEffect(() => {
    if (!runs.length) {
      setSelectedRunId("");
      return;
    }
    if (!runs.some((item) => item.id === selectedRunId)) {
      setSelectedRunId(runs[0].id);
    }
  }, [runs, selectedRunId]);

  const selectedRun = runs.find((item) => item.id === selectedRunId) || runs[0] || null;

  useEffect(() => {
    if (!selectedRun) {
      return;
    }
    actionForm.setFieldsValue({
      linkedTaskId: selectedRun.linkedTaskId || "",
      riskLevel: selectedRun.riskLevel || "medium",
      note: "",
    });
  }, [actionForm, selectedRun]);

  const alertList = useMemo(() => safeArray(ruleData.alerts), [ruleData.alerts]);

  async function submitCreate(values) {
    const response = await onCreateRun(values);
    if (response?.run?.id) {
      setSelectedRunId(response.run.id);
    }
    createForm.resetFields();
    setCreateOpen(false);
  }

  async function runAction(action) {
    if (!selectedRun) return;
    const values = await actionForm.validateFields();
    setBusyAction(action);
    try {
      await onUpdateRun({
        runId: selectedRun.id,
        action,
        note: values.note || "",
        linkedTaskId: values.linkedTaskId || selectedRun.linkedTaskId || "",
        riskLevel: values.riskLevel || selectedRun.riskLevel || "medium",
      });
      actionForm.setFieldsValue({ note: "" });
    } finally {
      setBusyAction("");
    }
  }

  async function submitRule(values) {
    await onSaveRule(values);
    ruleForm.resetFields();
    setRuleOpen(false);
  }

  async function submitChannel(values) {
    await onSaveChannel(values);
    channelForm.resetFields();
    setChannelOpen(false);
  }

  async function runChannelTest() {
    const values = await channelForm.validateFields();
    await onTestChannel(values);
  }

  if (!permissions.read) {
    return <Alert type="warning" showIcon message="当前账号没有查看端到端管理数据的权限。" />;
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <section className="overview-hero">
        <div className="overview-hero-copy">
          <Text className="section-kicker">Closed-Loop Operations</Text>
          <Title level={1}>把任务推进、策略触发、运行健康和告警通知，收口到一套运营闭环。</Title>
          <Paragraph>
            这一页现在不只是管理 Run。你可以在这里配置自动化规则、看 Agent 健康评分、回顾近一周吞吐和瓶颈，并把关键事件推送到飞书或 Telegram。
          </Paragraph>
          <div className="overview-meta-strip">
            <span>运行中 Run：{management.summary?.active || 0}</span>
            <span>活动规则：{ruleData.summary?.activeRules || 0}</span>
            <span>开放告警：{ruleData.summary?.openAlerts || 0}</span>
          </div>
        </div>

        <div className="overview-hero-board">
          <div className="hero-metric">
            <Text className="hero-metric-value">
              {healthData.summary?.averageScore || 0}
              <span>/100</span>
            </Text>
            <Text className="hero-metric-label">平均健康分</Text>
          </div>
          <div className="hero-metric">
            <Text className="hero-metric-value">
              {reportData.weekly?.completed || 0}
              <span>条</span>
            </Text>
            <Text className="hero-metric-label">7 日完成吞吐</Text>
          </div>
          <div className="hero-metric">
            <Text className="hero-metric-value">
              {ruleData.summary?.activeChannels || 0}
              <span>个</span>
            </Text>
            <Text className="hero-metric-label">通知通道</Text>
          </div>
        </div>
      </section>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={6}>
          <Card className="signal-card">
            <Statistic title="推进中 Run" value={management.summary?.active || 0} suffix="条" />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card className="signal-card">
            <Statistic title="规则命中待处理" value={ruleData.summary?.openAlerts || 0} suffix="条" />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card className="signal-card">
            <Statistic title="已发送通知" value={ruleData.summary?.notifiedAlerts || 0} suffix="条" />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card className="signal-card">
            <Statistic title="Relay 次数" value={reportData.weekly?.relayCount || 0} suffix="次/7d" />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card
            title="端到端 Run 管理"
            extra={
              permissions.taskWrite ? (
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                  新建 Run
                </Button>
              ) : null
            }
          >
            <Table
              rowKey="id"
              dataSource={runs}
              pagination={false}
              scroll={{ x: true }}
              locale={{ emptyText: <Empty description="还没有端到端管理 Run" /> }}
              onRow={(record) => ({
                onClick: () => {
                  setSelectedRunId(record.id);
                  actionForm.setFieldsValue({
                    linkedTaskId: record.linkedTaskId || "",
                    riskLevel: record.riskLevel || "medium",
                    note: "",
                  });
                },
              })}
              columns={[
                { title: "Run", dataIndex: "title", ellipsis: true },
                { title: "状态", dataIndex: "status", width: 120, render: (value) => statusTag(value) },
                { title: "当前阶段", dataIndex: "stageLabel", width: 140, ellipsis: true },
                { title: "风险", dataIndex: "riskLevel", width: 110, render: (value) => riskTag(value) },
                { title: "联动任务", dataIndex: "linkedTaskId", width: 150, ellipsis: true },
                { title: "更新时间", dataIndex: "updatedAgo", width: 120 },
              ]}
            />
          </Card>
        </Col>

        <Col xs={24} xl={10}>
          <Card title="Run 详情" className="workspace-card">
            {!selectedRun ? (
              <Empty description="选中一条 Run 后查看详情" />
            ) : (
              <Space direction="vertical" size={16} style={{ width: "100%" }}>
                <div>
                  <Space wrap size={8}>
                    <Tag icon={<DeploymentUnitOutlined />} color="processing">
                      {selectedRun.id}
                    </Tag>
                    {statusTag(selectedRun.status)}
                    {riskTag(selectedRun.riskLevel)}
                  </Space>
                  <Title level={4} style={{ marginTop: 12, marginBottom: 8 }}>
                    {selectedRun.title}
                  </Title>
                  <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                    {selectedRun.goal || "这条 Run 还没有补充业务目标。"}
                  </Paragraph>
                </div>

                <Steps
                  direction="vertical"
                  current={stageIndex(selectedRun)}
                  items={safeArray(selectedRun.stages).map((stage) => ({
                    title: stage.title,
                    description: stage.note || "暂无阶段备注",
                    status: stage.status === "done" ? "finish" : stage.status === "blocked" ? "error" : stage.status === "active" ? "process" : "wait",
                  }))}
                />

                <Card size="small" title="联动资产">
                  <List
                    dataSource={[
                      selectedRun.linkedTask
                        ? {
                            title: `任务 · ${selectedRun.linkedTask.id}`,
                            description: selectedRun.linkedTask.title,
                            action: (
                              <Button size="small" onClick={() => onSelectTask(selectedRun.linkedTask.id)}>
                                打开任务
                              </Button>
                            ),
                          }
                        : null,
                      selectedRun.linkedSession
                        ? {
                            title: `会话 · ${selectedRun.linkedSession.label}`,
                            description: selectedRun.linkedSession.preview || "打开会话查看 transcript",
                            action: (
                              <Button size="small" onClick={() => onOpenConversation(selectedRun.linkedSession)}>
                                打开会话
                              </Button>
                            ),
                          }
                        : null,
                      selectedRun.deliverable
                        ? {
                            title: `交付物 · ${selectedRun.deliverable.id}`,
                            description: selectedRun.deliverable.output || selectedRun.deliverable.summary || "已归档交付物",
                            action: <Tag color="success" icon={<CheckCircleOutlined />}>已归档</Tag>,
                          }
                        : null,
                    ].filter(Boolean)}
                    locale={{ emptyText: "当前还没有绑定任务、会话或交付物。" }}
                    renderItem={(item) => (
                      <List.Item extra={item.action}>
                        <List.Item.Meta title={item.title} description={item.description} />
                      </List.Item>
                    )}
                  />
                </Card>

                {permissions.taskWrite ? (
                  <Card size="small" title="推进动作">
                    <Form form={actionForm} layout="vertical">
                      <Form.Item label="阶段备注" name="note">
                        <TextArea rows={3} placeholder="记录当前卡点、推进说明或验收结果" />
                      </Form.Item>
                      <Form.Item label="联动任务" name="linkedTaskId">
                        <Select
                          allowClear
                          showSearch
                          optionFilterProp="label"
                          options={tasks.map((task) => ({ value: task.id, label: `${task.id} · ${task.title}` }))}
                        />
                      </Form.Item>
                      <Form.Item label="风险等级" name="riskLevel">
                        <Select
                          options={[
                            { value: "low", label: "LOW" },
                            { value: "medium", label: "MEDIUM" },
                            { value: "high", label: "HIGH" },
                          ]}
                        />
                      </Form.Item>
                      <Space wrap>
                        <Button type="primary" loading={busyAction === "advance"} onClick={() => runAction("advance")}>
                          推进下一阶段
                        </Button>
                        <Button danger loading={busyAction === "block"} onClick={() => runAction("block")}>
                          标记阻塞
                        </Button>
                        <Button loading={busyAction === "resume"} onClick={() => runAction("resume")}>
                          恢复推进
                        </Button>
                        <Button icon={<WarningOutlined />} loading={busyAction === "note"} onClick={() => runAction("note")}>
                          更新备注
                        </Button>
                        <Button loading={busyAction === "complete"} onClick={() => runAction("complete")}>
                          直接收口
                        </Button>
                      </Space>
                    </Form>
                  </Card>
                ) : null}
              </Space>
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={10}>
          <Card
            title="自动化规则"
            extra={
              permissions.taskWrite ? (
                <Space size={8}>
                  <Button onClick={onBootstrapRules}>初始化默认规则</Button>
                  <Button icon={<PlusOutlined />} onClick={() => setRuleOpen(true)}>新增规则</Button>
                </Space>
              ) : null
            }
          >
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <Descriptions size="small" column={2}>
                <Descriptions.Item label="活动规则">{ruleData.summary?.activeRules || 0}</Descriptions.Item>
                <Descriptions.Item label="可用通道">{ruleData.summary?.activeChannels || 0}</Descriptions.Item>
                <Descriptions.Item label="待处理告警">{ruleData.summary?.openAlerts || 0}</Descriptions.Item>
                <Descriptions.Item label="已通知">{ruleData.summary?.notifiedAlerts || 0}</Descriptions.Item>
              </Descriptions>
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                scroll={{ x: true }}
                dataSource={safeArray(ruleData.rules)}
                locale={{ emptyText: "还没有自动化规则。" }}
                columns={[
                  { title: "规则", dataIndex: "name", ellipsis: true },
                  { title: "触发器", dataIndex: "triggerType", width: 160, render: triggerTypeLabel },
                  { title: "阈值", dataIndex: "thresholdMinutes", width: 100, render: (value) => `${value || 0} 分钟` },
                  { title: "级别", dataIndex: "severity", width: 100, render: severityTag },
                  { title: "状态", dataIndex: "status", width: 100, render: (value) => statusTag(value === "active" ? "active" : "waiting") },
                ]}
              />
            </Space>
          </Card>
        </Col>

        <Col xs={24} xl={14}>
          <Card
            title="告警与通知"
            extra={permissions.adminWrite ? <Button icon={<BellOutlined />} onClick={() => setChannelOpen(true)}>配置通道</Button> : null}
          >
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <List
                size="small"
                dataSource={safeArray(ruleData.channels)}
                locale={{ emptyText: "还没有通知通道。先配置飞书、Telegram 或 Webhook。" }}
                renderItem={(channel) => (
                  <List.Item
                    extra={
                      <Space size={8}>
                        <Tag color={channel.status === "active" ? "success" : "default"}>{channel.status}</Tag>
                        <Tag>{channelTypeLabel(channel.type)}</Tag>
                      </Space>
                    }
                  >
                    <List.Item.Meta
                      title={channel.name}
                      description={`${channelTypeLabel(channel.type)} · ${channel.target || "未填写目标"}`}
                    />
                  </List.Item>
                )}
              />
              <List
                itemLayout="vertical"
                dataSource={alertList}
                locale={{ emptyText: "当前还没有命中的运营告警。" }}
                renderItem={(item) => (
                  <List.Item
                    extra={
                      <Space direction="vertical" size={8} align="end">
                        {severityTag(item.severity)}
                        <Tag color={item.status === "resolved" ? "success" : item.status === "notified" ? "processing" : "warning"}>
                          {String(item.status || "open").toUpperCase()}
                        </Tag>
                      </Space>
                    }
                  >
                    <List.Item.Meta
                      title={
                        <Space wrap size={8}>
                          <span>{item.title}</span>
                          {item.ruleName ? <Tag>{item.ruleName}</Tag> : null}
                        </Space>
                      }
                      description={`${item.detail || "暂无详细说明"} · ${item.triggeredAt || ""}`}
                    />
                    {safeArray(item.deliveries).length ? (
                      <Space wrap size={8}>
                        {item.deliveries.map((delivery) => (
                          <Tag key={`${item.id}-${delivery.channelId}`} color={delivery.outcome === "success" ? "success" : "error"}>
                            {delivery.channelName || delivery.channelId} · {delivery.outcome}
                          </Tag>
                        ))}
                      </Space>
                    ) : (
                      <Text type="secondary">当前还没有发送记录，适合先配置通知通道。</Text>
                    )}
                  </List.Item>
                )}
              />
            </Space>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={10}>
          <Card title="Agent 健康度评分" extra={<RadarChartOutlined />}>
            <List
              dataSource={safeArray(healthData.agents)}
              locale={{ emptyText: "当前还没有可评分的 Agent 数据。" }}
              renderItem={(agent) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space wrap size={8}>
                        <span>{agent.title}</span>
                        {bandTag(agent.band)}
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={8} style={{ width: "100%" }}>
                        <Progress
                          percent={agent.score}
                          showInfo
                          strokeColor={scoreStroke(agent.score)}
                          format={(value) => `${value} 分`}
                        />
                        <Space wrap size={12}>
                          <Text type="secondary">完成率 {agent.completionRate}%</Text>
                          <Text type="secondary">阻塞率 {agent.blockRate}%</Text>
                          <Text type="secondary">平均响应 {agent.avgResponseSeconds || 0}s</Text>
                        </Space>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>

        <Col xs={24} xl={14}>
          <Card title="运营报表 / 周报">
            <Space direction="vertical" size={16} style={{ width: "100%" }}>
              <Space wrap size={8}>
                <Button onClick={onExportReport}>导出本周周报</Button>
                <Text type="secondary">导出后会在本地 dashboard 目录生成 Markdown 周报。</Text>
              </Space>
              <Row gutter={[12, 12]}>
                <Col xs={12} md={6}>
                  <Card size="small">
                    <Statistic title="7 日完成" value={reportData.weekly?.completed || 0} suffix="条" />
                  </Card>
                </Col>
                <Col xs={12} md={6}>
                  <Card size="small">
                    <Statistic title="阻塞触点" value={reportData.weekly?.blockedTouches || 0} suffix="次" />
                  </Card>
                </Col>
                <Col xs={12} md={6}>
                  <Card size="small">
                    <Statistic title="协同信号" value={reportData.weekly?.signals || 0} suffix="条" />
                  </Card>
                </Col>
                <Col xs={12} md={6}>
                  <Card size="small">
                    <Statistic title="接力链路" value={reportData.weekly?.relayCount || 0} suffix="次" />
                  </Card>
                </Col>
              </Row>

              <Table
                size="small"
                pagination={false}
                scroll={{ x: true }}
                rowKey="date"
                dataSource={safeArray(reportData.daily)}
                columns={[
                  { title: "日期", dataIndex: "date", width: 90 },
                  { title: "完成", dataIndex: "completed", width: 80 },
                  { title: "阻塞触点", dataIndex: "blocked", width: 100 },
                  { title: "活动信号", dataIndex: "signals", width: 100 },
                ]}
              />

              <Row gutter={[16, 16]}>
                <Col xs={24} md={12}>
                  <Card size="small" title="本周瓶颈">
                    <List
                      size="small"
                      dataSource={safeArray(reportData.bottlenecks)}
                      locale={{ emptyText: "本周还没有明显瓶颈。" }}
                      renderItem={(item) => (
                        <List.Item>
                          <List.Item.Meta title={item.title} description={item.detail} />
                        </List.Item>
                      )}
                    />
                  </Card>
                </Col>
                <Col xs={24} md={12}>
                  <Card size="small" title="协作链路 Top 5">
                    <List
                      size="small"
                      dataSource={safeArray(reportData.relayLeaders)}
                      locale={{ emptyText: "最近还没有形成明显的接力链路。" }}
                      renderItem={(item) => (
                        <List.Item extra={<Tag>{item.count} 次</Tag>}>
                          <List.Item.Meta title={item.route} description={`最近一次 ${item.lastAgo || "刚刚"}`} />
                        </List.Item>
                      )}
                    />
                  </Card>
                </Col>
              </Row>
            </Space>
          </Card>
        </Col>
      </Row>

      <Modal open={createOpen} title="新建端到端管理 Run" okText="创建 Run" onCancel={() => setCreateOpen(false)} onOk={() => createForm.submit()} destroyOnClose>
        <Form form={createForm} layout="vertical" onFinish={submitCreate}>
          <Form.Item label="Run 标题" name="title" rules={[{ required: true, message: "请输入 Run 标题" }]}>
            <Input placeholder="例如：商城 MVP 发布闭环" />
          </Form.Item>
          <Form.Item label="业务目标" name="goal">
            <TextArea rows={3} placeholder="这条 Run 要完成什么结果、交付给谁、何时验收" />
          </Form.Item>
          <Form.Item label="负责人" name="owner">
            <Input placeholder="例如：Ops Lead / 产品负责人" />
          </Form.Item>
          <Form.Item label="联动任务" name="linkedTaskId">
            <Select allowClear showSearch optionFilterProp="label" options={tasks.map((task) => ({ value: task.id, label: `${task.id} · ${task.title}` }))} />
          </Form.Item>
          <Form.Item label="联动 Agent" name="linkedAgentId">
            <Select allowClear showSearch optionFilterProp="label" options={agents.map((agent) => ({ value: agent.id, label: `${agent.title} · ${agent.id}` }))} />
          </Form.Item>
          <Form.Item label="联动会话" name="linkedSessionKey">
            <Select allowClear showSearch optionFilterProp="label" options={sessions.map((session) => ({ value: session.key, label: session.label }))} />
          </Form.Item>
          <Form.Item label="发布渠道" name="releaseChannel" initialValue="manual">
            <Select options={[{ value: "manual", label: "手工收口" }, { value: "telegram", label: "Telegram" }, { value: "feishu", label: "Feishu" }, { value: "github-release", label: "GitHub Release" }]} />
          </Form.Item>
          <Form.Item label="风险等级" name="riskLevel" initialValue="medium">
            <Select options={[{ value: "low", label: "LOW" }, { value: "medium", label: "MEDIUM" }, { value: "high", label: "HIGH" }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal open={ruleOpen} title="新增自动化规则" okText="保存规则" onCancel={() => setRuleOpen(false)} onOk={() => ruleForm.submit()} destroyOnClose>
        <Form form={ruleForm} layout="vertical" onFinish={submitRule} initialValues={{ thresholdMinutes: 30, cooldownMinutes: 60, severity: "warning", triggerType: "blocked_task_timeout", status: "active" }}>
          <Form.Item label="规则名称" name="name" rules={[{ required: true, message: "请输入规则名称" }]}>
            <Input placeholder="例如：阻塞 30 分钟自动升级" />
          </Form.Item>
          <Form.Item label="说明" name="description">
            <TextArea rows={2} placeholder="说明这条规则什么时候应该触发，以及期望团队怎么响应。" />
          </Form.Item>
          <Form.Item label="触发类型" name="triggerType" rules={[{ required: true, message: "请选择触发类型" }]}>
            <Select
              options={[
                { value: "blocked_task_timeout", label: "阻塞超时自动升级" },
                { value: "critical_task_done", label: "关键任务完成通知" },
                { value: "agent_offline", label: "Agent 离线告警" },
              ]}
            />
          </Form.Item>
          <Form.Item label="阈值（分钟）" name="thresholdMinutes">
            <Input type="number" min={0} />
          </Form.Item>
          <Form.Item label="冷却时间（分钟）" name="cooldownMinutes">
            <Input type="number" min={0} />
          </Form.Item>
          <Form.Item label="严重级别" name="severity">
            <Select options={[{ value: "info", label: "INFO" }, { value: "warning", label: "WARNING" }, { value: "critical", label: "CRITICAL" }]} />
          </Form.Item>
          <Form.Item label="关键词 / 标记" name="matchText">
            <Input placeholder="例如：S级、P0、release-blocker" />
          </Form.Item>
          <Form.Item label="通知通道" name="channelIds">
            <Select
              mode="multiple"
              allowClear
              options={safeArray(ruleData.channels).map((channel) => ({
                value: channel.id,
                label: `${channel.name} · ${channelTypeLabel(channel.type)}`,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal open={channelOpen} title="配置通知通道" okText="保存通道" onCancel={() => setChannelOpen(false)} onOk={() => channelForm.submit()} destroyOnClose footer={permissions.adminWrite ? [
        <Button key="test" icon={<ThunderboltOutlined />} onClick={runChannelTest}>发送测试</Button>,
        <Button key="cancel" onClick={() => setChannelOpen(false)}>取消</Button>,
        <Button key="submit" type="primary" onClick={() => channelForm.submit()}>保存通道</Button>,
      ] : null}>
        <Form form={channelForm} layout="vertical" onFinish={submitChannel} initialValues={{ type: "feishu", status: "active" }}>
          <Form.Item label="通道名称" name="name" rules={[{ required: true, message: "请输入通道名称" }]}>
            <Input placeholder="例如：运营值班群" />
          </Form.Item>
          <Form.Item label="通道类型" name="type" rules={[{ required: true, message: "请选择通道类型" }]}>
            <Select options={[{ value: "feishu", label: "Feishu" }, { value: "telegram", label: "Telegram" }, { value: "webhook", label: "Webhook" }]} />
          </Form.Item>
          <Form.Item label="目标地址 / Chat ID" name="target" rules={[{ required: true, message: "请输入目标地址或 Chat ID" }]}>
            <Input placeholder="Feishu 填 webhook；Telegram 填 chat id；Webhook 填 URL" />
          </Form.Item>
          <Form.Item label="Secret / Bot Token" name="secret">
            <Input.Password placeholder="Telegram 需要 bot token；Webhook / Feishu 可留空" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

export default ManagementView;
