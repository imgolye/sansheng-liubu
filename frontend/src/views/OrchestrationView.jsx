import { useEffect, useMemo, useState } from "react";
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
  Progress,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { ApartmentOutlined, DeploymentUnitOutlined, PartitionOutlined, PlusOutlined, RetweetOutlined } from "@ant-design/icons";
import { safeArray, statusTag } from "../ui.jsx";

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

function contextRiskTag(risk) {
  const map = { good: "success", watch: "warning", high: "error" };
  return <Tag color={map[risk] || "default"}>{String(risk || "unknown").toUpperCase()}</Tag>;
}

function OrchestrationView({ dashboard, agents, permissions, onSaveWorkflow, onSavePolicy }) {
  const orchestration = dashboard.orchestration || { summary: {}, workflows: [], routingPolicies: [], replays: [], contextHotspots: [] };
  const workflows = safeArray(orchestration.workflows);
  const policies = safeArray(orchestration.routingPolicies);
  const replays = safeArray(orchestration.replays);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState(workflows[0]?.id || "");
  const [selectedReplayId, setSelectedReplayId] = useState(replays[0]?.taskId || "");
  const [workflowDraft, setWorkflowDraft] = useState(null);
  const [policyOpen, setPolicyOpen] = useState(false);
  const [policyForm] = Form.useForm();

  useEffect(() => {
    if (!workflows.length) {
      setSelectedWorkflowId("");
      setWorkflowDraft(null);
      return;
    }
    if (!workflows.some((item) => item.id === selectedWorkflowId)) {
      setSelectedWorkflowId(workflows[0].id);
    }
  }, [workflows, selectedWorkflowId]);

  useEffect(() => {
    const current = workflows.find((item) => item.id === selectedWorkflowId) || workflows[0] || null;
    setWorkflowDraft(current ? JSON.parse(JSON.stringify(current)) : null);
  }, [selectedWorkflowId, workflows]);

  useEffect(() => {
    if (!replays.length) {
      setSelectedReplayId("");
      return;
    }
    if (!replays.some((item) => item.taskId === selectedReplayId)) {
      setSelectedReplayId(replays[0].taskId);
    }
  }, [replays, selectedReplayId]);

  const selectedReplay = replays.find((item) => item.taskId === selectedReplayId) || replays[0] || null;
  const lanes = safeArray(workflowDraft?.lanes);
  const nodes = safeArray(workflowDraft?.nodes);
  const [dragNodeId, setDragNodeId] = useState("");

  const laneGroups = useMemo(
    () =>
      lanes.map((lane) => ({
        ...lane,
        nodes: nodes.filter((node) => node.laneId === lane.id),
      })),
    [lanes, nodes],
  );

  function updateNode(nodeId, patch) {
    setWorkflowDraft((current) => ({
      ...(current || {}),
      nodes: safeArray(current?.nodes).map((node) => (node.id === nodeId ? { ...node, ...patch } : node)),
    }));
  }

  function moveNode(nodeId, targetLaneId, targetIndex) {
    setWorkflowDraft((current) => {
      const currentNodes = safeArray(current?.nodes);
      const moving = currentNodes.find((node) => node.id === nodeId);
      if (!moving) return current;
      const remaining = currentNodes.filter((node) => node.id !== nodeId);
      const laneNodes = remaining.filter((node) => node.laneId === targetLaneId);
      const before = remaining.filter((node) => node.laneId !== targetLaneId);
      const updatedLaneNodes = [...laneNodes];
      updatedLaneNodes.splice(targetIndex, 0, { ...moving, laneId: targetLaneId });
      return {
        ...(current || {}),
        nodes: [...before, ...updatedLaneNodes],
      };
    });
  }

  async function saveWorkflow() {
    if (!workflowDraft) return;
    await onSaveWorkflow(workflowDraft);
  }

  async function submitPolicy(values) {
    await onSavePolicy(values);
    policyForm.resetFields();
    setPolicyOpen(false);
  }

  if (!permissions.read) {
    return <Alert type="warning" showIcon message="当前账号没有查看协作编排数据的权限。" />;
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <section className="overview-hero">
        <div className="overview-hero-copy">
          <Text className="section-kicker">Agent Orchestration IDE</Text>
          <Title level={1}>把多 Agent 协作逻辑从 SOUL 文本里拉出来，变成可看、可调、可回放的产品层能力。</Title>
          <Paragraph>
            这里面同时做四件事：定义任务流、查看完整协作回放、配置动态路由规则，以及找出上下文在哪一步丢了。
          </Paragraph>
          <div className="overview-meta-strip">
            <span>工作流：{orchestration.summary?.workflowCount || 0}</span>
            <span>动态策略：{orchestration.summary?.activePolicies || 0}</span>
            <span>上下文热点：{orchestration.summary?.contextLossHotspots || 0}</span>
          </div>
        </div>

        <div className="overview-hero-board">
          <div className="hero-metric">
            <Text className="hero-metric-value">{orchestration.summary?.replayCount || 0}<span>条</span></Text>
            <Text className="hero-metric-label">可回放任务</Text>
          </div>
          <div className="hero-metric">
            <Text className="hero-metric-value">{(orchestration.summary?.strategyBreakdown || {}).keyword_department || 0}<span>条</span></Text>
            <Text className="hero-metric-label">关键词路由</Text>
          </div>
          <div className="hero-metric">
            <Text className="hero-metric-value">{(orchestration.summary?.strategyBreakdown || {}).load_balance || 0}<span>条</span></Text>
            <Text className="hero-metric-label">负载策略</Text>
          </div>
        </div>
      </section>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card
            title="可视化编排器"
            extra={
              permissions.taskWrite ? (
                <Space size={8}>
                  <Select
                    value={selectedWorkflowId || undefined}
                    style={{ width: 220 }}
                    onChange={setSelectedWorkflowId}
                    options={workflows.map((item) => ({ value: item.id, label: item.name }))}
                  />
                  <Button type="primary" onClick={saveWorkflow}>保存编排</Button>
                </Space>
              ) : null
            }
          >
            {!workflowDraft ? (
              <Empty description="当前还没有可编辑的协作工作流。" />
            ) : (
              <Space direction="vertical" size={16} style={{ width: "100%" }}>
                <div>
                  <Title level={4} style={{ marginBottom: 6 }}>{workflowDraft.name}</Title>
                  <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                    {workflowDraft.description || "把工程、质量、运维等阶段排成一条可解释的协作流。"}
                  </Paragraph>
                </div>

                <div className="orch-lanes">
                  {laneGroups.map((lane) => (
                    <div
                      key={lane.id}
                      className="orch-lane"
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event) => {
                        event.preventDefault();
                        if (dragNodeId) {
                          moveNode(dragNodeId, lane.id, lane.nodes.length);
                          setDragNodeId("");
                        }
                      }}
                    >
                      <div className="orch-lane-head">
                        <strong>{lane.title}</strong>
                        <span>{lane.subtitle}</span>
                      </div>
                      <Space direction="vertical" size={10} style={{ width: "100%" }}>
                        {lane.nodes.map((node, index) => (
                          <div
                            key={node.id}
                            className="orch-node-card"
                            draggable={permissions.taskWrite}
                            onDragStart={() => setDragNodeId(node.id)}
                            onDragOver={(event) => event.preventDefault()}
                            onDrop={(event) => {
                              event.preventDefault();
                              if (dragNodeId) {
                                moveNode(dragNodeId, lane.id, index);
                                setDragNodeId("");
                              }
                            }}
                          >
                            <div className="orch-node-top">
                              <Tag icon={<ApartmentOutlined />} color="processing">{node.title}</Tag>
                              {statusTag(workflowDraft.status)}
                            </div>
                            <Select
                              size="small"
                              value={node.agentId || undefined}
                              style={{ width: "100%" }}
                              disabled={!permissions.taskWrite}
                              onChange={(value) => updateNode(node.id, { agentId: value })}
                              options={agents.map((agent) => ({ value: agent.id, label: `${agent.title} · ${agent.id}` }))}
                            />
                            <Input.TextArea
                              value={node.handoffNote || ""}
                              autoSize={{ minRows: 2, maxRows: 4 }}
                              disabled={!permissions.taskWrite}
                              onChange={(event) => updateNode(node.id, { handoffNote: event.target.value })}
                              placeholder="这一跳要传递什么上下文？"
                            />
                          </div>
                        ))}
                      </Space>
                    </div>
                  ))}
                </div>
              </Space>
            )}
          </Card>
        </Col>

        <Col xs={24} xl={10}>
          <Card
            title="动态路由策略"
            extra={permissions.taskWrite ? <Button icon={<PlusOutlined />} onClick={() => setPolicyOpen(true)}>新增策略</Button> : null}
          >
            <Table
              rowKey="id"
              dataSource={policies}
              pagination={false}
              scroll={{ x: true }}
              locale={{ emptyText: "当前还没有动态路由策略。" }}
              columns={[
                { title: "策略", dataIndex: "name", ellipsis: true },
                { title: "类型", dataIndex: "strategyType", width: 130, render: (value) => <Tag>{value}</Tag> },
                { title: "关键词", dataIndex: "keyword", width: 120, ellipsis: true },
                { title: "目标 Agent", dataIndex: "targetAgentId", width: 120 },
                { title: "优先级", dataIndex: "priorityLevel", width: 100, render: (value) => <Tag color="gold">{String(value || "").toUpperCase()}</Tag> },
              ]}
            />
            <List
              style={{ marginTop: 16 }}
              size="small"
              dataSource={safeArray(orchestration.commands)}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta title={item.label} description={item.description} />
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card
            title="协作回放"
            extra={
              <Select
                value={selectedReplayId || undefined}
                style={{ width: 280 }}
                onChange={setSelectedReplayId}
                options={replays.map((item) => ({ value: item.taskId, label: `${item.taskId} · ${item.title}` }))}
              />
            }
          >
            {!selectedReplay ? (
              <Empty description="当前没有可回放任务。" />
            ) : (
              <Space direction="vertical" size={16} style={{ width: "100%" }}>
                <div>
                  <Space wrap size={8}>
                    <Tag icon={<DeploymentUnitOutlined />} color="processing">{selectedReplay.taskId}</Tag>
                    {statusTag(selectedReplay.state)}
                    <Tag icon={<RetweetOutlined />}>{selectedReplay.route?.length || 0} hops</Tag>
                    <Tag>{selectedReplay.durationMinutes || 0} min</Tag>
                  </Space>
                  <Title level={4} style={{ marginTop: 12, marginBottom: 6 }}>{selectedReplay.title}</Title>
                  <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                    发起人 {selectedReplay.initiator || "未知"} · 当前负责人 {selectedReplay.owner || "未知"} · 最近更新 {selectedReplay.updatedAgo || "刚刚"}
                  </Paragraph>
                </div>

                <List
                  itemLayout="vertical"
                  dataSource={safeArray(selectedReplay.entries)}
                  locale={{ emptyText: "这条任务还没有形成完整的协作轨迹。" }}
                  renderItem={(entry) => (
                    <List.Item
                      extra={
                        <Space direction="vertical" size={8} align="end">
                          <Tag>{entry.kind}</Tag>
                          {entry.durationToNextMinutes ? <Tag color="blue">+{entry.durationToNextMinutes} min</Tag> : null}
                        </Space>
                      }
                    >
                      <List.Item.Meta
                        title={entry.headline}
                        description={`${entry.atAgo || ""}${entry.at ? ` · ${entry.at}` : ""}`}
                      />
                      <Space direction="vertical" size={8} style={{ width: "100%" }}>
                        <Paragraph style={{ marginBottom: 0 }}>{entry.detail || "这一跳没有留下更多说明。"}</Paragraph>
                        <div className="orch-context-packet">
                          <strong>上下文包</strong>
                          {contextRiskTag(entry.contextPacket?.risk)}
                          <span>{entry.contextPacket?.summary}</span>
                        </div>
                      </Space>
                    </List.Item>
                  )}
                />
              </Space>
            )}
          </Card>
        </Col>

        <Col xs={24} xl={10}>
          <Card title="跨 Agent 上下文透传">
            <List
              dataSource={safeArray(orchestration.contextHotspots)}
              locale={{ emptyText: "当前还没有明显的上下文丢失热点。" }}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space wrap size={8}>
                        <span>{item.taskId}</span>
                        <Tag color="warning">{item.contextLossCount} 风险点</Tag>
                      </Space>
                    }
                    description={`${item.title} · ${item.owner || "未知负责人"} · ${item.durationMinutes || 0} min`}
                  />
                </List.Item>
              )}
            />

            <Card size="small" style={{ marginTop: 16 }} title="当前工作流覆盖率">
              <Progress
                percent={Math.min(100, ((orchestration.summary?.workflowCount || 0) * 25) + ((orchestration.summary?.activePolicies || 0) * 10))}
                strokeColor="#7d3511"
                format={(value) => `${value}%`}
              />
              <Paragraph type="secondary" style={{ marginTop: 10, marginBottom: 0 }}>
                覆盖率越高，说明更多调度和协作逻辑已经从 Agent 文本约定提升成产品层配置。
              </Paragraph>
            </Card>
          </Card>
        </Col>
      </Row>

      <Modal open={policyOpen} title="新增动态路由策略" okText="保存策略" onCancel={() => setPolicyOpen(false)} onOk={() => policyForm.submit()} destroyOnClose>
        <Form
          form={policyForm}
          layout="vertical"
          onFinish={submitPolicy}
          initialValues={{ status: "active", strategyType: "keyword_department", priorityLevel: "normal" }}
        >
          <Form.Item label="策略名称" name="name" rules={[{ required: true, message: "请输入策略名称" }]}>
            <Input placeholder="例如：包含 bugfix 关键字时直达工部" />
          </Form.Item>
          <Form.Item label="策略类型" name="strategyType" rules={[{ required: true, message: "请选择策略类型" }]}>
            <Select
              options={[
                { value: "keyword_department", label: "关键词 -> 部门映射" },
                { value: "load_balance", label: "负载均衡" },
                { value: "priority_queue", label: "优先级队列" },
              ]}
            />
          </Form.Item>
          <Form.Item label="关键词" name="keyword">
            <Input placeholder="例如：release / bugfix / billing" />
          </Form.Item>
          <Form.Item label="目标 Agent" name="targetAgentId" rules={[{ required: true, message: "请选择目标 Agent" }]}>
            <Select options={agents.map((agent) => ({ value: agent.id, label: `${agent.title} · ${agent.id}` }))} />
          </Form.Item>
          <Form.Item label="优先级" name="priorityLevel">
            <Select
              options={[
                { value: "low", label: "LOW" },
                { value: "normal", label: "NORMAL" },
                { value: "high", label: "HIGH" },
                { value: "critical", label: "CRITICAL" },
              ]}
            />
          </Form.Item>
          <Form.Item label="队列名称" name="queueName">
            <Input placeholder="例如：release-fast-lane" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

export default OrchestrationView;
