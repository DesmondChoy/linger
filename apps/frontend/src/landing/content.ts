/**
 * Everything the landing page says, in one place.
 *
 * Edit the words here; colours and spacing come from the tokens at the top of
 * `src/index.css`. Set `enabled: false` to hide a path from the landing page.
 */
export const landing = {
  brandMark: 'L',
  title: 'Linger',
  tagline: 'Notice what stays with you.',
  intro:
    'Linger is a reading companion that helps you reflect on what you read, ' +
    'grounded in the book and in what you have chosen to remember.',

  live: {
    enabled: true,
    heading: 'Live experience',
    body: 'Sign in and talk with Linger yourself. Your chats and memories are kept to your account.',
    signInLabel: 'Sign in',
    signUpLabel: 'Create account',
    switchToSignUp: 'New here? Create an account',
    switchToSignIn: 'Already have an account? Sign in',
    continueLabel: (username: string) => `Continue as ${username}`,
    signOutLabel: 'Sign out',
  },

  synthetic: {
    enabled: true,
    heading: 'Synthetic personas',
    body:
      'Replay recorded conversations from synthetic readers and see how each agent ' +
      'handled every scene. No sign-in needed.',
    openLabel: 'Explore saved evaluations',
  },

  footer: 'A course prototype. Accounts are for testing only; do not enter sensitive information.',
}
