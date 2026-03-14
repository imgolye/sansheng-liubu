import { Card, Col, List, Row, Statistic, Table, Timeline, Typography } from "antd";
import { metricCards, safeArray, statusTag } from "../ui.jsx";

const { Title, Paragraph, Text } = Typography;

function OverviewView({ dashboard, agents, tasks }) {
  const topMetrics = metricCards(dashboard.metrics).slice(0, 3);
  const flowMetrics = metricCards(dashboard.metrics).slice(3);

  return (
    <div className="overview-shell">
      <section className="overview-hero">
        <div className="overview-hero-copy">
          <Text className="section-kicker">Control Plane Snapshot</Text>
          <Title level={1}>把协同现场、交付风险和会话压力，压缩到一张经营首页。</Title>
          <Paragraph>
            这一页不是简单的数据堆叠，而是给运营负责人快速判断节奏的工作台。先看当下是否稳，再决定往哪里点进去处理。
          </Paragraph>
          <div className="overview-meta-strip">
            <span>主题：{dashboard.theme?.displayName || "未知主题"}</span>
            <span>路由：{dashboard.routerAgentId || "router"}</span>
            <span>同步：{dashboard.generatedAgo || "刚刚"}</span>
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

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card className="workspace-card" title="Agent 现场" extra={<Text type="secondary">{agents.length} 个</Text>}>
            <Table
              size="small"
              pagination={false}
              rowKey="id"
              columns={[
                { title: "Agent", dataIndex: "title" },
                { title: "状态", dataIndex: "status", render: (value) => statusTag(value) },
                { title: "任务", dataIndex: "activeTasks" },
                { title: "阻塞", dataIndex: "blockedTasks" },
                { title: "最近信号", dataIndex: "lastSeenAgo" },
              ]}
              dataSource={agents.slice(0, 8)}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="workspace-card" title="交付河道" extra={<Text type="secondary">{tasks.length} 条</Text>}>
            <Table
              size="small"
              pagination={false}
              rowKey="id"
              columns={[
                { title: "任务", dataIndex: "id" },
                { title: "标题", dataIndex: "title", ellipsis: true },
                { title: "状态", dataIndex: "state", render: (value) => statusTag(value) },
                { title: "负责人", dataIndex: "currentAgentLabel", ellipsis: true },
              ]}
              dataSource={tasks.slice(0, 8)}
            />
          </Card>
        </Col>

        <Col xs={24} xl={14}>
          <Card className="workspace-card" title="最近活动">
            <Timeline
              items={safeArray(dashboard.events).slice(0, 8).map((event) => ({
                color: event.type === "progress" ? "green" : "orange",
                children: (
                  <div>
                    <Text strong>{event.headline || event.title}</Text>
                    <br />
                    <Text type="secondary">{event.detail || "无额外信息"}</Text>
                  </div>
                ),
              }))}
            />
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card className="workspace-card" title="需要你留意的信号">
            <List
              dataSource={[
                {
                  title: "阻塞任务",
                  detail: `${dashboard.metrics?.blockedTasks || 0} 条任务需要治理动作`,
                },
                {
                  title: "交接节奏",
                  detail: `最近 24h 完成 ${dashboard.metrics?.handoffs24h || 0} 次 handoff`,
                },
                {
                  title: "会话热度",
                  detail: `最近 1h 收到 ${dashboard.metrics?.signals1h || 0} 条协同信号`,
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
