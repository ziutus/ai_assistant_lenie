import React from "react";
import ReactDOM from "react-dom/client";
import "./modules/shared/styles/index.css";
import App from "./App";
import { BrowserRouter as Router } from "react-router-dom";
import AuthorizationProvider from "./modules/shared/context/authorizationContext";

const root = ReactDOM.createRoot(document.getElementById("root") as HTMLElement);
root.render(
  <React.StrictMode>
    <AuthorizationProvider>
      <Router>
        <App />
      </Router>
    </AuthorizationProvider>
  </React.StrictMode>,
);
