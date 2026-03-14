import { Button, Card, Col, Descriptions, Row, Tag, Typography } from "antd";
import { safeArray } from "../ui.jsx";

const { Paragraph } = Typography;

function ThemesView({ dashboard, permissions, onSwitchTheme, t }) {
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={8}>
        <Card title={t("themes.currentTitle")} className="workspace-card">
          <Descriptions column={1} size="small">
            <Descriptions.Item label={t("themes.name")}>{dashboard.theme?.displayName}</Descriptions.Item>
            <Descriptions.Item label={t("themes.themeId")}>{dashboard.theme?.name}</Descriptions.Item>
            <Descriptions.Item label={t("themes.router")}>{dashboard.routerAgentId}</Descriptions.Item>
          </Descriptions>
        </Card>
      </Col>
      <Col xs={24} xl={16}>
        <Card title={t("themes.catalogTitle")} className="workspace-card">
          <Row gutter={[16, 16]}>
            {safeArray(dashboard.themeCatalog).map((theme) => (
              <Col xs={24} md={12} key={theme.name}>
                <Card
                  size="small"
                  title={theme.displayName}
                  extra={theme.current ? <Tag color="success">{t("themes.current")}</Tag> : <Tag>{theme.name}</Tag>}
                >
                  <Paragraph>{theme.summary}</Paragraph>
                  <Paragraph type="secondary">{theme.bestFor}</Paragraph>
                  {permissions.themeWrite && !theme.current ? (
                    <Button onClick={() => onSwitchTheme(theme.name)}>{t("themes.switch")}</Button>
                  ) : null}
                </Card>
              </Col>
            ))}
          </Row>
        </Card>
      </Col>
    </Row>
  );
}

export default ThemesView;
