import type { Metadata } from "next";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { NavigationTracker } from "@/components/NavigationTracker";
import "./globals.css";

export const metadata: Metadata = {
  title: "GNK ALGO — Intelligence behind every trade",
  description: "Algo platform for the Indian stock market. Connect Dhan and Groww, run strategies, AI signals, and webhooks.",
  icons: {
    icon: "/gnkalgo-brand.png",
    apple: "/gnkalgo-brand.png",
  },
};

const themeInitScript = `
(function() {
  try {
    var t = localStorage.getItem('gnk_theme') || 'background-1';
    document.documentElement.setAttribute('data-theme', t);
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="background-1" suppressHydrationWarning>
      <head>
        <script>{themeInitScript}</script>
      </head>
      <body className="antialiased min-h-screen">
        <NavigationTracker />
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
