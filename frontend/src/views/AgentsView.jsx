import { Card, Col, Grid, Progress, Row, Segmented, Space, Table, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import NextStepCard from "../components/NextStepCard.jsx";
import { statusTag } from "../ui.jsx";

const { Text, Paragraph } = Typography;
const { useBreakpoint } = Grid;

function loadScore(agent) {
  return Math.min(100, agent.activeTasks * 25 + agent.blockedTasks * 18 + agent.handoffs24h * 2);
}

function AgentsView({ agents, onSelectAgent, onNavigate, t }) {
  const screens = useBreakpoint();
  const isCompact = !screens.lg;
  const [mode, setMode] = useState(isCompact ? "cards" : "table");

  useEffect(() => {
    setMode(isCompact ? "cards" : "table");
  }, [isCompact]);
  const columns = useMemo(
    () => [
      { title: t("overview.columns.agent"), dataIndex: "title", width: 180 },
      { title: t("agents.name"), dataIndex: "name", width: 180 },
      { title: t("overview.columns.status"), dataIndex: "status", width: 120, render: (value) => statusTag(value) },
      { title: t("agents.active"), dataIndex: "activeTasks", width: 120 },
      { title: t("overview.columns.blocked"), dataIndex: "blockedTasks", width: 100 },
      { title: t("agents.handoffs"), dataIndex: "handoffs24h", width: 120 },
      { title: t("agents.focus"), dataIndex: "focus", ellipsis: true },
      { title: t("overview.columns.recentSignal"), dataIndex: "lastSeenAgo", width: 120 },
    ],
    [t],
  );

  if (!agents.length) {
    return (
      <NextStepCard
        title={t("guides.agents.title")}
        description={t("guides.agents.description")}
        steps={[t("guides.agents.step1"), t("guides.agents.step2"), t("guides.agents.step3")]}
        actionLabel={t("guides.agents.action")}
        onAction={() => onNavigate?.("/themes")}
        iconText="A"
      />
    );
  }

  return (
    <Card
      title={t("agents.title")}
      extra={
        <Space>
          <Text type="secondary">{t("agents.modeHint")}</Text>
          <Segmented
            value={mode}
            onChange={(value) => setMode(String(value))}
            options={[
              { value: "table", label: t("agents.table") },
              { value: "cards", label: t("agents.cards") },
            ]}
          />
        </Space>
      }
      className="workspace-card"
    >
      {mode === "table" ? (
        <Table
          rowKey="id"
          dataSource={agents}
          scroll={{ x: 980 }}
          onRow={(record) => ({
            onClick: () => onSelectAgent(record.id),
          })}
          columns={columns}
        />
      ) : (
        <Row gutter={[16, 16]}>
          {agents.map((agent) => (
            <Col xs={24} md={12} xl={8} key={agent.id}>
              <button type="button" className="agent-card-button" onClick={() => onSelectAgent(agent.id)}>
                <div className="agent-card-shell">
                  <div className="agent-card-head">
                    <div>
                      <Text strong>{agent.title}</Text>
                      <Paragraph type="secondary" ellipsis={{ rows: 1 }}>
                        {agent.name}
                      </Paragraph>
                    </div>
                    {statusTag(agent.status)}
                  </div>
                  <div className="agent-card-metrics">
                    <span>{agent.activeTasks} {t("agents.activeShort")}</span>
                    <span>{agent.blockedTasks} {t("agents.blockedShort")}</span>
                    <span>{agent.handoffs24h} {t("agents.handoffShort")}</span>
                  </div>
                  <Progress percent={loadScore(agent)} showInfo={false} strokeColor="#b55a2a" trailColor="rgba(181, 90, 42, 0.12)" />
                  <Text type="secondary">{t("agents.load")} {loadScore(agent)}%</Text>
                  <Paragraph className="agent-card-focus" ellipsis={{ rows: 2 }}>
                    {agent.focus || t("agents.noFocus")}
                  </Paragraph>
                  <Text type="secondary">{agent.lastSeenAgo}</Text>
                </div>
              </button>
            </Col>
          ))}
        </Row>
      )}
    </Card>
  );
}

export default AgentsView;
