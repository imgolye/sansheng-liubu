import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Steps,
  Table,
  Tag,
  Typography,
} from "antd";
import { CheckCircleOutlined, DeploymentUnitOutlined, PlusOutlined, WarningOutlined } from "@ant-design/icons";
import { safeArray, statusTag } from "../ui.jsx";

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

function riskTag(level) {
  const normalized = String(level || "medium").toLowerCase();
  const color = normalized === "high" ? "error" : normalized === "low" ? "success" : "warning";
  return <Tag color={color}>{normalized.toUpperCase()}</Tag>;
}

function stageIndex(run) {
  return Math.max(
    0,
    safeArray(run?.stages).findIndex((stage) => stage.key === run?.stageKey),
  );
}

function ManagementView({ dashboard, permissions, agents, tasks, sessions, onCreateRun, onUpdateRun, onSelectTask, onOpenConversation }) {
  const management = dashboard.management || { summary: {}, runs: [] };
  const runs = safeArray(management.runs);
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState(runs[0]?.id || "");
  const [busyAction, setBusyAction] = useState("");
  const [createForm] = Form.useForm();
  const [actionForm] = Form.useForm();

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

  async function submitCreate(values) {
    const response = await onCreateRun(values);
    if (response?.run?.id) {
      setSelectedRunId(response.run.id);
    }
    createForm.resetFields();
    setCreateOpen(false);
  }

  async function runAction(action) {
    if (!selectedRun) {
      return;
    }
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

  if (!permissions.read) {
    return <Alert type="warning" showIcon message="当前账号没有查看端到端管理数据的权限。" />;
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <section className="overview-hero">
        <div className="overview-hero-copy">
          <Text className="section-kicker">End-to-End Command</Text>
          <Title level={1}>把立项、执行、验证和发布，压成一条可管理的 Run。</Title>
          <Paragraph>
            这一页不是再看一遍任务列表，而是专门管理一条交付链。每个 Run 都有当前阶段、风险、联动任务和会话，方便负责人快速做推进决策。
          </Paragraph>
          <div className="overview-meta-strip">
            <span>总 Run：{management.summary?.total || 0}</span>
            <span>活跃：{management.summary?.active || 0}</span>
            <span>待发布：{management.summary?.readyForRelease || 0}</span>
          </div>
        </div>

        <div className="overview-hero-board">
          <div className="hero-metric">
            <Text className="hero-metric-value">
              {management.summary?.active || 0}
              <span>条</span>
            </Text>
            <Text className="hero-metric-label">推进中</Text>
          </div>
          <div className="hero-metric">
            <Text className="hero-metric-value">
              {management.summary?.blocked || 0}
              <span>条</span>
            </Text>
            <Text className="hero-metric-label">受阻</Text>
          </div>
          <div className="hero-metric">
            <Text className="hero-metric-value">
              {management.summary?.completed || 0}
              <span>条</span>
            </Text>
            <Text className="hero-metric-label">已收口</Text>
          </div>
        </div>
      </section>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <Card className="signal-card">
            <Statistic title="进行中 Run" value={management.summary?.active || 0} suffix="条" />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card className="signal-card">
            <Statistic title="验证 / 发布阶段" value={management.summary?.readyForRelease || 0} suffix="条" />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card className="signal-card">
            <Statistic title="高风险 Run" value={(management.summary?.riskBreakdown || {}).high || 0} suffix="条" />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card
            title="端到端管理台"
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
                    <Form
                      form={actionForm}
                      layout="vertical"
                      initialValues={{
                        linkedTaskId: selectedRun.linkedTaskId || "",
                        riskLevel: selectedRun.riskLevel || "medium",
                        note: "",
                      }}
                    >
                      <Form.Item label="阶段备注" name="note">
                        <TextArea rows={3} placeholder="记录当前卡点、推进说明或验收结果" />
                      </Form.Item>
                      <Form.Item label="联动任务" name="linkedTaskId">
                        <Select
                          allowClear
                          showSearch
                          optionFilterProp="label"
                          options={tasks.map((task) => ({
                            value: task.id,
                            label: `${task.id} · ${task.title}`,
                          }))}
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

      <Modal
        open={createOpen}
        title="新建端到端管理 Run"
        okText="创建 Run"
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        destroyOnClose
      >
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
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={tasks.map((task) => ({
                value: task.id,
                label: `${task.id} · ${task.title}`,
              }))}
            />
          </Form.Item>
          <Form.Item label="联动 Agent" name="linkedAgentId">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={agents.map((agent) => ({
                value: agent.id,
                label: `${agent.title} · ${agent.id}`,
              }))}
            />
          </Form.Item>
          <Form.Item label="联动会话" name="linkedSessionKey">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={sessions.map((session) => ({
                value: session.key,
                label: session.label,
              }))}
            />
          </Form.Item>
          <Form.Item label="发布渠道" name="releaseChannel" initialValue="manual">
            <Select
              options={[
                { value: "manual", label: "手工收口" },
                { value: "telegram", label: "Telegram" },
                { value: "feishu", label: "Feishu" },
                { value: "github-release", label: "GitHub Release" },
              ]}
            />
          </Form.Item>
          <Form.Item label="风险等级" name="riskLevel" initialValue="medium">
            <Select
              options={[
                { value: "low", label: "LOW" },
                { value: "medium", label: "MEDIUM" },
                { value: "high", label: "HIGH" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

export default ManagementView;
