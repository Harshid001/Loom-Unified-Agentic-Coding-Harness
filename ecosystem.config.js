module.exports = {
  apps: [
    {
      name: "loom-api",
      script: "loom",
      args: "server --port 8000",
      interpreter: "python",
      env: {
        NODE_ENV: "development",
        PORT: 8000
      },
      env_production: {
        NODE_ENV: "production",
        PORT: 8000
      }
    },
    {
      name: "loom-web",
      script: "npm",
      args: "run dev",
      cwd: "./web",
      env: {
        PORT: 3000
      },
      env_production: {
        PORT: 3000,
        NODE_ENV: "production",
        args: "run start"
      }
    }
  ]
};
