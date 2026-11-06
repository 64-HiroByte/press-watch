export const testBasicAuth = { username: "presswatch-test", password: "local-test-only" };

export const testBasicAuthEnv = {
  PRESSWATCH_BASIC_AUTH_USER: testBasicAuth.username,
  PRESSWATCH_BASIC_AUTH_PASSWORD: testBasicAuth.password,
};
