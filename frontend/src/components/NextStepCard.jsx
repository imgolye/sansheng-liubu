import { Button, Card, Empty, Space, Typography } from "antd";

const { Paragraph, Text } = Typography;

function NextStepCard({ title, description, steps = [], actionLabel = "", onAction, iconText = "->" }) {
  return (
    <Card className="workspace-card next-step-card">
      <Space direction="vertical" size={14} style={{ width: "100%" }}>
        <div className="next-step-head">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={false} />
          <Text className="next-step-icon">{iconText}</Text>
        </div>
        <div>
          <Text className="next-step-title">{title}</Text>
          <Paragraph className="next-step-description">{description}</Paragraph>
        </div>
        <div className="next-step-list">
          {steps.map((step, index) => (
            <div className="next-step-item" key={`${title}-${index}`}>
              <span>{index + 1}</span>
              <Text>{step}</Text>
            </div>
          ))}
        </div>
        {actionLabel && onAction ? (
          <Button type="primary" onClick={onAction}>
            {actionLabel}
          </Button>
        ) : null}
      </Space>
    </Card>
  );
}

export default NextStepCard;
