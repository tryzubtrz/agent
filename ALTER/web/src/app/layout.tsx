import type { Metadata, Viewport } from "next";
import OwnerGate from "@/components/OwnerGate";
import ApprovalCenter from "@/components/ApprovalCenter";
import ModuleRouteBridge from "@/components/ModuleRouteBridge";
import Telemetry from "@/components/Telemetry";
import ToolLauncher from "@/components/ToolLauncher";
import "./globals.css";

export const metadata: Metadata = {
  title: "ALTER",
  description: "Owner-controlled AI control plane",
  applicationName: "ALTER",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
  appleWebApp: {
    capable: true,
    title: "ALTER",
    statusBarStyle: "black-translucent"
  },
  formatDetection: { telephone: false }
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
  themeColor: "#050608"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="uk">
      <body>
        <OwnerGate>
          {children}
          <ApprovalCenter />
          <ModuleRouteBridge />
          <Telemetry />
          <ToolLauncher />
        </OwnerGate>
      </body>
    </html>
  );
}
