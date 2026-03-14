import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App as AntdApp } from "antd";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AntdApp>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AntdApp>
  </React.StrictMode>,
);
