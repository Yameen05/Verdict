import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AuthGate } from "./components/AuthGate";
import "./styles/index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthGate>
      {(session, logout) => (
        <App
          userEmail={session.user.email}
          userRole={session.user.role}
          onLogout={logout}
        />
      )}
    </AuthGate>
  </React.StrictMode>,
);
