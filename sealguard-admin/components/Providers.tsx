"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, theme } from "antd";
import { useState } from "react";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: "#c1121f",
          colorSuccess: "#2d6a4f",
          colorWarning: "#f48c06",
          colorError: "#9d0208",
          colorBgLayout: "#f4f3ef",
          colorTextBase: "#1a1a1a",
          borderRadius: 12,
        },
      }}
    >
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ConfigProvider>
  );
}
