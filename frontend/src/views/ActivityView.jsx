import { Card, Col, Row, Timeline, Typography } from "antd";
import { safeArray } from "../ui.jsx";
import { ActivityTrendPanel, buildActivityTrend, RelayNetworkPanel } from "../components/DataCharts.jsx";

const { Text } = Typography;

function ActivityView({ dashboard, t }) {
  const trendData = buildActivityTrend(safeArray(dashboard.events));

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={10}>
        <Card title={t("activity.relayTitle")} className="workspace-card">
          <RelayNetworkPanel
            relays={safeArray(dashboard.relays)}
            emptyText={t("activity.emptyRelay")}
            edgeLabel={t("activity.handoffCount")}
          />
        </Card>
      </Col>
      <Col xs={24} xl={14}>
        <Card title={t("activity.trendTitle")} className="workspace-card">
          <ActivityTrendPanel data={trendData} emptyText={t("overview.charts.emptyTrend")} />
        </Card>
      </Col>
      <Col xs={24}>
        <Card title={t("activity.timelineTitle")} className="workspace-card">
          <Timeline
            items={safeArray(dashboard.events).map((event) => ({
              color: event.type === "progress" ? "green" : "orange",
              children: (
                <div>
                  <Text strong>{event.headline || event.title}</Text>
                  <br />
                  <Text type="secondary">{event.detail || t("activity.noDetail")}</Text>
                </div>
              ),
            }))}
          />
        </Card>
      </Col>
    </Row>
  );
}

export default ActivityView;
