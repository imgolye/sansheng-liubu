import { Form, Input, Modal } from "antd";

const { TextArea } = Input;

function CreateTaskModal({ open, onCancel, onAction }) {
  const [form] = Form.useForm();

  return (
    <Modal
      title="创建任务"
      open={open}
      onCancel={() => {
        form.resetFields();
        onCancel();
      }}
      onOk={() => form.submit()}
      okText="创建并进入任务"
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={async (values) => {
          await onAction("/api/actions/task/create", values);
          form.resetFields();
          onCancel();
        }}
      >
        <Form.Item label="任务标题" name="title" rules={[{ required: true, message: "请输入任务标题" }]}>
          <Input placeholder="例如：梳理今天还未收口的事项" />
        </Form.Item>
        <Form.Item label="备注" name="remark">
          <TextArea rows={4} placeholder="可选。写一些创建上下文，方便中书省签收。" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default CreateTaskModal;
