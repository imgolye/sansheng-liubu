import { Card, Col, List, Row, Statistic, Table, Typography } from "antd";
import { formatListText, safeArray, statusTag } from "../ui.jsx";

const { Text } = Typography;

function OpenClawView({ dashboard, t }) {
  return (
    <>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12} xl={6}>
          <Card className="workspace-card">
            <Statistic title={t("openclaw.version")} value={dashboard.openclaw?.version?.release || "unknown"} />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card className="workspace-card">
            <Statistic title={t("openclaw.nativeSkills")} value={dashboard.openclaw?.nativeSkills?.total || 0} />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card className="workspace-card">
            <Statistic title={t("openclaw.eligibleSkills")} value={dashboard.openclaw?.nativeSkills?.eligible || 0} />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card className="workspace-card">
            <Statistic title={t("openclaw.healthyChannels")} value={safeArray(dashboard.openclaw?.gateway?.channels).filter((item) => item.healthy).length} />
          </Card>
        </Col>
      </Row>
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={10}>
          <Card title={t("openclaw.compatibility")} className="workspace-card">
            <List
              dataSource={safeArray(dashboard.openclaw?.compatibility)}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <>
                        <Text strong>{item.title}</Text> {statusTag(item.status)}
                      </>
                    }
                    description={formatListText([item.body, item.meta])}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} xl={14}>
          <Card title={t("openclaw.gateway")} className="workspace-card">
            <Table
              size="small"
              rowKey="title"
              pagination={false}
              dataSource={safeArray(dashboard.openclaw?.gateway?.channels)}
              columns={[
                { title: t("openclaw.channel"), dataIndex: "title" },
                { title: t("openclaw.config"), dataIndex: "meta" },
                { title: t("openclaw.running"), dataIndex: "running", render: (value) => (value ? statusTag("ready") : statusTag("warning")) },
                { title: t("openclaw.detail"), dataIndex: "detail", ellipsis: true },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </>
  );
}

export default OpenClawView;
