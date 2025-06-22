// app.config.js
module.exports = {
  common: {
    autoUpdate: true,
    multiWindow: true,
    defaultTheme: 'dark'
  },
  development: {
    devTools: true,
    hotReload: true,
    logLevel: 'debug'
  },
  production: {
    devTools: false,
    hotReload: false,
    logLevel: 'error'
  }
};
