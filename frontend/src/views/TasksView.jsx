import { useEffect, useState } from "react";
import { Button, Card, Grid, List, Segmented, Space, Table, Tag, Typography } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import NextStepCard from "../components/NextStepCard.jsx";
import { formatListText, safeArray, statusTag } from "../ui.jsx";

const { Text, Paragraph } = Typography;
const { useBreakpoint } = Grid;

function taskPreview(task, t) {
  return formatListText([
    task.currentAgentLabel || "",
    task.updatedAgo || "",
    task.owner || "",
  ]) || t("tasks.noProgress");
}

function TasksView({ permissions, tasks, dashboard, onOpenCreateTask, onSelectTask, t }) {
  const screens = useBreakpoint();
  const isCompact = !screens.lg;
  const [mode, setMode] = useState(isCompact ? "cards" : "table");

  useEffect(() => {
    setMode(isCompact ? "cards" : "table");
  }, [isCompact]);

  const taskGuide = (
    <NextStepCard
      title={t("guides.tasks.title")}
      description={t("guides.tasks.description")}
      steps={[t("guides.tasks.step1"), t("guides.tasks.step2"), t("guides.tasks.step3")]}
      actionLabel={permissions.taskWrite ? t("guides.tasks.action") : t("guides.tasks.secondaryAction")}
      onAction={permissions.taskWrite ? onOpenCreateTask : undefined}
      iconText="T"
    />
  );

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card
        title={t("tasks.title")}
        extra={
          <Space>
            <Text type="secondary">{t("tasks.modeHint")}</Text>
            <Segmented
              size="small"
              value={mode}
              onChange={(value) => setMode(String(value))}
              options={[
                { value: "table", label: t("tasks.table") },
                { value: "cards", label: t("tasks.cards") },
              ]}
            />
            {permissions.taskWrite ? (
              <Button type="primary" icon={<PlusOutlined />} onClick={onOpenCreateTask}>
                {t("tasks.create")}
              </Button>
            ) : null}
          </Space>
        }
        className="workspace-card"
      >
        {!tasks.length ? taskGuide : mode === "table" ? (
          <Table
            rowKey="id"
            dataSource={tasks}
            locale={{ emptyText: t("tasks.emptyTasks") }}
            scroll={{ x: 860 }}
            onRow={(record) => ({
              onClick: () => onSelectTask(record.id),
            })}
            columns={[
              { title: t("tasks.columns.id"), dataIndex: "id", width: 180 },
              { title: t("tasks.columns.title"), dataIndex: "title", ellipsis: true },
              { title: t("tasks.columns.state"), dataIndex: "state", width: 120, render: (value) => statusTag(value) },
              { title: t("tasks.columns.owner"), dataIndex: "currentAgentLabel", width: 160, ellipsis: true },
              { title: t("tasks.columns.official"), dataIndex: "owner", width: 140, ellipsis: true },
              { title: t("tasks.columns.updated"), dataIndex: "updatedAgo", width: 120 },
            ]}
          />
        ) : (
          <List
            grid={{ gutter: 16, xs: 1, md: 2 }}
            dataSource={tasks}
            locale={{ emptyText: t("tasks.emptyTasks") }}
            renderItem={(item) => (
              <List.Item>
                <button type="button" className="task-card-button" onClick={() => onSelectTask(item.id)}>
                  <Card className="task-card-shell" bordered={false}>
                    <Space direction="vertical" size={12} style={{ width: "100%" }}>
                      <Space wrap size={8}>
                        <Tag color="processing">{item.id}</Tag>
                        {statusTag(item.state)}
                      </Space>
                      <div>
                        <Text strong>{item.title || t("tasks.untitled")}</Text>
                        <Paragraph type="secondary" className="task-card-meta">
                          {taskPreview(item, t)}
                        </Paragraph>
                      </div>
                      <div className="task-card-grid">
                        <div>
                          <Text type="secondary">{t("tasks.currentOwner")}</Text>
                          <Text>{item.currentAgentLabel || "-"}</Text>
                        </div>
                        <div>
                          <Text type="secondary">{t("tasks.ownerSignoff")}</Text>
                          <Text>{item.owner || "-"}</Text>
                        </div>
                        <div>
                          <Text type="secondary">{t("tasks.updatedLabel")}</Text>
                          <Text>{item.updatedAgo || "-"}</Text>
                        </div>
                        <div>
                          <Text type="secondary">{t("tasks.lastProgress")}</Text>
                          <Text>{item.progress || t("tasks.noProgress")}</Text>
                        </div>
                      </div>
                      <Text className="task-card-cta">{t("tasks.openTask")}</Text>
                    </Space>
                  </Card>
                </button>
              </List.Item>
            )}
          />
        )}
      </Card>

      <Card title={t("tasks.deliverables")} className="workspace-card">
        <List
          dataSource={safeArray(dashboard.deliverables)}
          locale={{ emptyText: t("tasks.emptyDeliverables") }}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta
                title={`${item.id} · ${item.title}`}
                description={formatListText([item.summary, item.output, item.updatedAgo])}
              />
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}

export default TasksView;
