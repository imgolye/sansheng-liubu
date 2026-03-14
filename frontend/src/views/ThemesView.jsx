import { Button, Card, Col, Descriptions, Row, Tag, Typography } from "antd";
import { safeArray } from "../ui.jsx";

const { Paragraph } = Typography;

function ThemesView({ dashboard, permissions, onSwitchTheme }) {
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={8}>
        <Card title="当前主题">
          <Descriptions column={1} size="small">
            <Descriptions.Item label="名称">{dashboard.theme?.displayName}</Descriptions.Item>
            <Descriptions.Item label="Theme ID">{dashboard.theme?.name}</Descriptions.Item>
            <Descriptions.Item label="当前路由 Agent">{dashboard.routerAgentId}</Descriptions.Item>
          </Descriptions>
        </Card>
      </Col>
      <Col xs={24} xl={16}>
        <Card title="主题目录">
          <Row gutter={[16, 16]}>
            {safeArray(dashboard.themeCatalog).map((theme) => (
              <Col xs={24} md={12} key={theme.name}>
                <Card
                  size="small"
                  title={theme.displayName}
                  extra={theme.current ? <Tag color="success">当前主题</Tag> : <Tag>{theme.name}</Tag>}
                >
                  <Paragraph>{theme.summary}</Paragraph>
                  <Paragraph type="secondary">{theme.bestFor}</Paragraph>
                  {permissions.themeWrite && !theme.current ? (
                    <Button onClick={() => onSwitchTheme(theme.name)}>切换到此主题</Button>
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
