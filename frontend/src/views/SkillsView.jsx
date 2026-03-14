import { Alert, Button, Card, Col, List, Row, Space, Statistic, Typography } from "antd";
import { safeArray, statusTag } from "../ui.jsx";

const { Text } = Typography;

function SkillsView({ dashboard, permissions, onPackageSkill, onPublishSkill }) {
  return (
    <Card title="Skills Center">
      {!dashboard.skills?.supported ? (
        <Alert type="warning" showIcon message={dashboard.skills?.error || "当前安装没有可用的 Skills 能力。"} />
      ) : (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={8}>
            <Card size="small">
              <Statistic title="本地技能" value={dashboard.skills?.summary?.total || 0} suffix="个" />
            </Card>
          </Col>
          <Col xs={24} xl={8}>
            <Card size="small">
              <Statistic title="Ready" value={dashboard.skills?.summary?.ready || 0} suffix="个" />
            </Card>
          </Col>
          <Col xs={24} xl={8}>
            <Card size="small">
              <Statistic title="已打包" value={dashboard.skills?.summary?.packaged || 0} suffix="个" />
            </Card>
          </Col>
          <Col xs={24}>
            <List
              dataSource={safeArray(dashboard.skills?.skills)}
              locale={{ emptyText: "当前没有可展示的技能。" }}
              renderItem={(item) => (
                <List.Item
                  actions={
                    permissions.adminWrite
                      ? [
                          <Button key="package" size="small" onClick={() => onPackageSkill(item.slug)}>
                            打包
                          </Button>,
                          <Button key="publish" size="small" onClick={() => onPublishSkill(item.slug)}>
                            发布到 OpenClaw
                          </Button>,
                        ]
                      : []
                  }
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <Text strong>{item.displayName || item.name}</Text>
                        {statusTag(item.status || "ready")}
                      </Space>
                    }
                    description={[item.slug, item.categoryLabel, item.relativePath].filter(Boolean).join(" · ")}
                  />
                </List.Item>
              )}
            />
          </Col>
        </Row>
      )}
    </Card>
  );
}

export default SkillsView;
