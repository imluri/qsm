"use strict";

// The greedy path match accepts both Windows drive letters and POSIX paths.
function parseCompilerError(message, fallbackPath) {
    const lines = message.trim().split(/\r?\n/);
    for (const line of lines) {
        const match = /^(.*):(\d+):\s*(.+)$/.exec(line);
        if (match) {
            return { path: match[1], line: Math.max(0, Number(match[2]) - 1), message: match[3] };
        }
    }
    return { path: fallbackPath, line: 0, message: message.trim() || "QSM compilation failed" };
}

module.exports = { parseCompilerError };
