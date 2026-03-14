import { Card, Col, List, Row, Statistic, Table, Timeline, Typography } from "antd";
import { metricCards, safeArray, statusTag } from "../ui.jsx";
import NextStepCard from "../components/NextStepCard.jsx";
import {
  ActivityTrendPanel,
  AgentLoadPanel,
  buildActivityTrend,
  buildAgentLoadData,
  buildTaskFunnel,
  FunnelPanel,
} from "../components/DataCharts.jsx";

const { Title, Paragraph, Text } = Typography;

function OverviewView({ dashboard, agents, tasks, sessions, onNavigate, onOpenCreateTask, t }) {
  const topMetrics = metricCards(dashboard.metrics).slice(0, 3);
  const flowMetrics = metricCards(dashboard.metrics).slice(3);
  const funnelData = buildTaskFunnel(tasks);
  const loadData = buildAgentLoadData(agents);
  const trendData = buildActivityTrend(safeArray(dashboard.events));
  const hasEmptyGuides = !agents.length || !tasks.length || !sessions.length;

  return (
    <div className="overview-shell">
      <section className="overview-hero">
        <div className="overview-hero-copy">
          <Text className="section-kicker">{t("overview.kicker")}</Text>
          <Title level={1}>{t("overview.title")}</Title>
          <Paragraph>{t("overview.summary")}</Paragraph>
          <div className="overview-meta-strip">
            <span>{t("overview.theme")}：{dashboard.theme?.displayName || "—"}</span>
            <span>{t("overview.router")}：{dashboard.routerAgentId || "router"}</span>
            <span>{t("overview.sync")}：{dashboard.generatedAgo || "—"}</span>
          </div>
        </div>

        <div className="overview-hero-board">
          {topMetrics.map((item) => (
            <div className="hero-metric" key={item.title}>
              <Text className="hero-metric-value">
                {item.value}
                <span>{item.suffix}</span>
              </Text>
              <Text className="hero-metric-label">{item.title}</Text>
            </div>
          ))}
        </div>
      </section>

      <Row gutter={[16, 16]}>
        {flowMetrics.map((item) => (
          <Col xs={24} md={8} key={item.title}>
            <Card className="signal-card">
              <Statistic title={item.title} value={item.value} suffix={item.suffix} />
            </Card>
          </Col>
        ))}
      </Row>

      {hasEmptyGuides ? (
        <Row gutter={[16, 16]}>
          {!tasks.length ? (
            <Col xs={24} xl={8}>
              <NextStepCard
                title={t("guides.tasks.title")}
                description={t("guides.tasks.description")}
                steps={[t("guides.tasks.step1"), t("guides.tasks.step2"), t("guides.tasks.step3")]}
                actionLabel={onOpenCreateTask ? t("guides.tasks.action") : t("guides.tasks.secondaryAction")}
                onAction={onOpenCreateTask || (() => onNavigate?.("/tasks"))}
                iconText="01"
              />
            </Col>
          ) : null}
          {!agents.length ? (
            <Col xs={24} xl={8}>
              <NextStepCard
                title={t("guides.agents.title")}
                description={t("guides.agents.description")}
                steps={[t("guides.agents.step1"), t("guides.agents.step2"), t("guides.agents.step3")]}
                actionLabel={t("guides.agents.action")}
                onAction={() => onNavigate?.("/themes")}
                iconText="02"
              />
            </Col>
          ) : null}
          {!sessions.length ? (
            <Col xs={24} xl={8}>
              <NextStepCard
                title={t("guides.conversations.title")}
                description={t("guides.conversations.description")}
                steps={[t("guides.conversations.step1"), t("guides.conversations.step2"), t("guides.conversations.step3")]}
                actionLabel={t("guides.conversations.action")}
                onAction={() => onNavigate?.("/conversations")}
                iconText="03"
              />
            </Col>
          ) : null}
        </Row>
      ) : null}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={8}>
          <Card className="workspace-card" title={t("overview.charts.funnel")}>
            <FunnelPanel data={funnelData} emptyText={t("overview.charts.emptyFunnel")} />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card className="workspace-card" title={t("overview.charts.heatmap")}>
            <AgentLoadPanel data={loadData} emptyText={t("overview.charts.emptyLoad")} />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card className="workspace-card" title={t("overview.charts.gantt")}>
            <ActivityTrendPanel data={trendData} emptyText={t("overview.charts.emptyTrend")} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card className="workspace-card" title={t("overview.agentBoard")} extra={<Text type="secondary">{agents.length} {t("overview.agentCountSuffix")}</Text>}>
            <Table
              size="small"
              pagination={false}
              rowKey="id"
              scroll={{ x: 620 }}
              columns={[
                { title: t("overview.columns.agent"), dataIndex: "title" },
                { title: t("overview.columns.status"), dataIndex: "status", render: (value) => statusTag(value) },
                { title: t("overview.columns.tasks"), dataIndex: "activeTasks" },
                { title: t("overview.columns.blocked"), dataIndex: "blockedTasks" },
                { title: t("overview.columns.recentSignal"), dataIndex: "lastSeenAgo" },
              ]}
              dataSource={agents.slice(0, 8)}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="workspace-card" title={t("overview.taskBoard")} extra={<Text type="secondary">{tasks.length} {t("overview.taskCountSuffix")}</Text>}>
            <Table
              size="small"
              pagination={false}
              rowKey="id"
              scroll={{ x: 620 }}
              columns={[
                { title: t("overview.columns.taskId"), dataIndex: "id" },
                { title: t("overview.columns.taskTitle"), dataIndex: "title", ellipsis: true },
                { title: t("overview.columns.status"), dataIndex: "state", render: (value) => statusTag(value) },
                { title: t("overview.columns.owner"), dataIndex: "currentAgentLabel", ellipsis: true },
              ]}
              dataSource={tasks.slice(0, 8)}
            />
          </Card>
        </Col>

        <Col xs={24} xl={14}>
          <Card className="workspace-card" title={t("overview.recentActivity")}>
            <Timeline
              items={safeArray(dashboard.events).slice(0, 8).map((event) => ({
                color: event.type === "progress" ? "green" : "orange",
                children: (
                  <div>
                    <Text strong>{event.headline || event.title}</Text>
                    <br />
                    <Text type="secondary">{event.detail || t("overview.columns.noDetail")}</Text>
                  </div>
                ),
              }))}
            />
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card className="workspace-card" title={t("overview.attention")}>
            <List
              dataSource={[
                {
                  title: t("overview.signals.blockedTitle"),
                  detail: `${dashboard.metrics?.blockedTasks || 0} ${t("overview.signals.blockedDetail")}`,
                },
                {
                  title: t("overview.signals.handoffTitle"),
                  detail: `${dashboard.metrics?.handoffs24h || 0} ${t("overview.signals.handoffDetail")}`,
                },
                {
                  title: t("overview.signals.sessionTitle"),
                  detail: `${dashboard.metrics?.signals1h || 0} ${t("overview.signals.sessionDetail")}`,
                },
              ]}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta title={item.title} description={item.detail} />
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}

export default OverviewView;
