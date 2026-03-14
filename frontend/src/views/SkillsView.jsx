import { Alert, Button, Card, Col, List, Row, Space, Statistic, Typography } from "antd";
import { safeArray, statusTag } from "../ui.jsx";

const { Text } = Typography;

function SkillsView({ dashboard, permissions, onPackageSkill, onPublishSkill, t }) {
  return (
    <Card title={t("skills.title")} className="workspace-card">
      {!dashboard.skills?.supported ? (
        <Alert type="warning" showIcon message={dashboard.skills?.error || t("skills.unsupported")} />
      ) : (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={8}>
            <Card size="small">
              <Statistic title={t("skills.total")} value={dashboard.skills?.summary?.total || 0} />
            </Card>
          </Col>
          <Col xs={24} xl={8}>
            <Card size="small">
              <Statistic title={t("skills.ready")} value={dashboard.skills?.summary?.ready || 0} />
            </Card>
          </Col>
          <Col xs={24} xl={8}>
            <Card size="small">
              <Statistic title={t("skills.packaged")} value={dashboard.skills?.summary?.packaged || 0} />
            </Card>
          </Col>
          <Col xs={24}>
            <List
              dataSource={safeArray(dashboard.skills?.skills)}
              locale={{ emptyText: t("skills.empty") }}
              renderItem={(item) => (
                <List.Item
                  actions={
                    permissions.adminWrite
                      ? [
                          <Button key="package" size="small" onClick={() => onPackageSkill(item.slug)}>
                            {t("skills.package")}
                          </Button>,
                          <Button key="publish" size="small" onClick={() => onPublishSkill(item.slug)}>
                            {t("skills.publish")}
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
