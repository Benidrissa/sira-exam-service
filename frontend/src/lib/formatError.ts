export function formatError(err: unknown): string {
  if (err instanceof Error) {
    const msg = err.message
    if (msg.includes("Failed to fetch") || msg.includes("NetworkError") || msg.includes("network"))
      return "Network error — check your connection and try again."
    if (msg.includes("401") || msg.includes("Unauthorized"))
      return "Your session has expired. Please log in again."
    if (msg.includes("403") || msg.includes("Forbidden"))
      return "You don't have permission to do this."
    if (msg.includes("404") || msg.includes("Not Found"))
      return "The requested item was not found."
    if (msg.includes("409") || msg.includes("Conflict"))
      return "This action conflicts with the current state. Please refresh and try again."
    if (msg.includes("422") || msg.includes("Unprocessable"))
      return "The submitted data is invalid. Please check your inputs."
    if (msg.includes("500") || msg.includes("Internal Server"))
      return "Something went wrong on our end. Please try again later."
  }
  return "An unexpected error occurred. Please refresh and try again."
}
