import { Card, Col, List, Row, Statistic, Table, Typography } from "antd";
import { formatListText, safeArray, statusTag } from "../ui.jsx";

const { Text } = Typography;

function OpenClawView({ dashboard }) {
  return (
    <>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12} xl={6}>
          <Card>
            <Statistic title="OpenClaw 版本" value={dashboard.openclaw?.version?.release || "unknown"} />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card>
            <Statistic title="原生 Skills" value={dashboard.openclaw?.nativeSkills?.total || 0} suffix="个" />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card>
            <Statistic title="可直接使用" value={dashboard.openclaw?.nativeSkills?.eligible || 0} suffix="个" />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card>
            <Statistic title="健康 Channel" value={safeArray(dashboard.openclaw?.gateway?.channels).filter((item) => item.healthy).length} suffix="个" />
          </Card>
        </Col>
      </Row>
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={10}>
          <Card title="兼容性判断">
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
          <Card title="Channels 与 Gateway">
            <Table
              size="small"
              rowKey="title"
              pagination={false}
              dataSource={safeArray(dashboard.openclaw?.gateway?.channels)}
              columns={[
                { title: "Channel", dataIndex: "title" },
                { title: "配置", dataIndex: "meta" },
                { title: "运行", dataIndex: "running", render: (value) => (value ? statusTag("ready") : statusTag("warning")) },
                { title: "详情", dataIndex: "detail", ellipsis: true },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </>
  );
}

export default OpenClawView;
