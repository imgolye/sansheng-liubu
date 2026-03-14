import { Card, Col, List, Row, Timeline, Typography } from "antd";
import { safeArray } from "../ui.jsx";

const { Text } = Typography;

function ActivityView({ dashboard }) {
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={10}>
        <Card title="接力关系">
          <List
            dataSource={safeArray(dashboard.relays)}
            locale={{ emptyText: "最近 24 小时还没有形成 handoff 网络。" }}
            renderItem={(relay) => (
              <List.Item>
                <List.Item.Meta
                  title={`${relay.from} → ${relay.to}`}
                  description={`次数 ${relay.count} · 最近 ${relay.lastAgo}`}
                />
              </List.Item>
            )}
          />
        </Card>
      </Col>
      <Col xs={24} xl={14}>
        <Card title="完整时间线">
          <Timeline
            items={safeArray(dashboard.events).map((event) => ({
              color: event.type === "progress" ? "green" : "orange",
              children: (
                <div>
                  <Text strong>{event.headline || event.title}</Text>
                  <br />
                  <Text type="secondary">{event.detail}</Text>
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
