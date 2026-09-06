function showVoiceActionError(message) {
    const banner = document.getElementById("voice-action-error");
    const text = document.getElementById("voice-action-error-text");
    if (!banner || !text) return;

    text.textContent = message;
    banner.style.display = "block";

    // Auto-hide after a few seconds so it doesn't linger forever.
    clearTimeout(showVoiceActionError._hideTimer);
    showVoiceActionError._hideTimer = setTimeout(() => {
        banner.style.display = "none";
    }, 6000);
}

function hideVoiceActionError() {
    const banner = document.getElementById("voice-action-error");
    if (banner) banner.style.display = "none";
}

document.addEventListener("DOMContentLoaded", () => {
    const widget = document.querySelector("elevenlabs-convai");

    if (widget) {
        // Register client tools inside the widget's "call" event, per
        // ElevenLabs' current widget-embed contract.
        widget.addEventListener("elevenlabs-convai:call", (event) => {
            event.detail.config.clientTools = {
                add_task: async ({ title, time, scheduled_time, scheduled_date, frequency, description }) => {
                    const payload = {
                        title: title || "",
                        description: description || "",
                        frequency: frequency || "one_time",
                        // The backend form field is "scheduled_time"; accept either
                        // name in case the agent passes "time" instead.
                        scheduled_time: scheduled_time || time || "",
                        // Required by the backend for anything other than one_time.
                        scheduled_date: scheduled_date || ""
                    };

                    console.log("add_task called with:", payload);

                    try {
                        // /elder/reminders already resolves the correct elder
                        // server-side (via the caregiver's session), so no
                        // elder id needs to be sent from the client.
                        const response = await fetch("/elder/reminders", {
                            method: "POST",
                            credentials: "same-origin",
                            headers: {
                                "Content-Type": "application/x-www-form-urlencoded",
                                // Lets the backend tell this apart from a normal
                                // browser form submit, so validation failures come
                                // back as a real error status instead of a
                                // redirect (which fetch would treat as success).
                                "X-Requested-With": "fetch"
                            },
                            body: new URLSearchParams(payload).toString()
                        });

                        // The route redirects back to a page on success/failure
                        // (it doesn't return JSON), so a followed redirect with
                        // an ok status is our success signal.
                        if (!response.ok) {
                            console.error("add_task request failed:", response.status);

                            let errorMessage = `Couldn't add the task (error ${response.status}).`;
                            if (response.status === 403) {
                                errorMessage = "You don't have permission to add tasks for this elder.";
                            } else if (response.status === 400) {
                                errorMessage = "That reminder is missing some required info (like a start date for repeating reminders).";
                            }

                            showVoiceActionError(errorMessage);
                            return { success: false, error: errorMessage };
                        }

                        hideVoiceActionError();
                        return { success: true };
                    } catch (err) {
                        console.error("add_task request error:", err);
                        const errorMessage = "Couldn't reach the server to add the task.";
                        showVoiceActionError(errorMessage);
                        return { success: false, error: errorMessage };
                    }
                }
            };
        });
    }
});