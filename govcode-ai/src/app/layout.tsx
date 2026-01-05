import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "GovCode AI",
    template: "%s · GovCode AI",
  },
  description:
    "GovCode AI is a secure, deployable AI coding and policy copilot platform for public-sector teams.",
  applicationName: "GovCode AI",
  metadataBase: new URL("http://localhost:3000"),
  robots: {
    index: false,
    follow: false,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body
        className={`${geistSans.variable} ${geistMono.variable} min-h-full bg-black text-zinc-100 antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
