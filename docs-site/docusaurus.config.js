// @ts-check

const config = {
  title: "RAGnos Docs",
  tagline: "Architecture, pipeline, and API reference for the local RAG app",
  url: "http://localhost",
  baseUrl: "/",
  onBrokenLinks: "throw",
  onBrokenMarkdownLinks: "warn",
  i18n: {
    defaultLocale: "en",
    locales: ["en"]
  },
  presets: [
    [
      "classic",
      {
        docs: {
          path: "docs",
          routeBasePath: "docs",
          sidebarPath: require.resolve("./sidebars.js")
        },
        blog: false,
        theme: {
          customCss: require.resolve("./src/css/custom.css")
        }
      }
    ]
  ],
  themeConfig: {
    navbar: {
      title: "RAGnos",
      items: [
        {
          type: "docSidebar",
          sidebarId: "documentationSidebar",
          position: "left",
          label: "Documentation"
        }
      ]
    },
    footer: {
      style: "dark",
      links: [
        {
          title: "Docs",
          items: [
            { label: "Introduction", to: "/docs/intro" },
            { label: "Architecture", to: "/docs/architecture" },
            { label: "Pipeline", to: "/docs/pipeline" },
            { label: "API Reference", to: "/docs/api-reference" }
          ]
        }
      ],
      copyright: `Copyright ${new Date().getFullYear()} RAGnos`
    }
  }
};

module.exports = config;
