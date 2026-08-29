import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ReconProvider } from "@/store/ReconProvider";
import { ThemeProvider } from "@/store/ThemeProvider";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <ReconProvider>
          <App />
        </ReconProvider>
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
);
