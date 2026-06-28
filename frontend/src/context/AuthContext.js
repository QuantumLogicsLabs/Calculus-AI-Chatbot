import { createContext, useContext, useState } from "react";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // null = guest. For history-tab testing, set a fake user:
  //user data
  // const [user] = useState({ username: "hassan", accessToken: "test-token" });
  const [user] = useState(null);

  return (
    <AuthContext.Provider value={{ user, login: () => {}, logout: () => {}, signup: () => {} }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}