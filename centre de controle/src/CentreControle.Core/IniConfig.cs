using System.Text;
using System.Text.RegularExpressions;

namespace CentreControle.Core;

public static class IniConfig
{
    public static Dictionary<string, Dictionary<string, string>> Read(string path)
    {
        var data = new Dictionary<string, Dictionary<string, string>>(StringComparer.OrdinalIgnoreCase);
        if (!File.Exists(path))
            return data;

        string currentSection = "";
        foreach (var rawLine in File.ReadAllLines(path, Encoding.UTF8))
        {
            var line = rawLine.Trim();
            if (line.Length == 0 || line.StartsWith('#') || line.StartsWith(';'))
                continue;

            if (line.StartsWith('[') && line.EndsWith(']'))
            {
                currentSection = line[1..^1].Trim();
                if (!data.ContainsKey(currentSection))
                    data[currentSection] = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                continue;
            }

            var eq = line.IndexOf('=');
            if (eq <= 0)
                continue;

            var key = line[..eq].Trim();
            var val = line[(eq + 1)..].Trim();
            if (!data.ContainsKey(currentSection))
                data[currentSection] = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            data[currentSection][key] = val;
        }

        return data;
    }

    public static string GetString(Dictionary<string, Dictionary<string, string>> data, string section, string key, string fallback = "")
    {
        if (data.TryGetValue(section, out var sec) && sec.TryGetValue(key, out var val))
            return val;
        return fallback;
    }

    public static bool GetBool(Dictionary<string, Dictionary<string, string>> data, string section, string key, bool fallback = false)
    {
        var s = GetString(data, section, key, "");
        if (string.IsNullOrWhiteSpace(s))
            return fallback;
        return s.Trim().ToLowerInvariant() switch
        {
            "1" or "true" or "yes" or "on" => true,
            "0" or "false" or "no" or "off" => false,
            _ => fallback,
        };
    }

    public static int GetInt(Dictionary<string, Dictionary<string, string>> data, string section, string key, int fallback = 0)
    {
        var s = GetString(data, section, key, "");
        return int.TryParse(s.Trim(), out var v) ? v : fallback;
    }

    public static bool PatchSection(string path, string section, IReadOnlyDictionary<string, string> updates)
    {
        try
        {
            var lines = File.Exists(path)
                ? File.ReadAllLines(path, Encoding.UTF8).ToList()
                : new List<string>();

            int secStart = -1;
            int secEnd = lines.Count;
            var secHeaderRegex = new Regex(@"^\s*\[([^\]]+)\]\s*$");

            for (int i = 0; i < lines.Count; i++)
            {
                var m = secHeaderRegex.Match(lines[i]);
                if (!m.Success)
                    continue;
                if (secStart >= 0)
                {
                    secEnd = i;
                    break;
                }
                if (m.Groups[1].Value.Trim().Equals(section, StringComparison.OrdinalIgnoreCase))
                    secStart = i;
            }

            if (secStart < 0)
            {
                if (lines.Count > 0 && !string.IsNullOrWhiteSpace(lines[^1]))
                    lines.Add("");
                lines.Add($"[{section}]");
                foreach (var kv in updates)
                    lines.Add($"{kv.Key} = {kv.Value}");
            }
            else
            {
                var pending = new Dictionary<string, string>(updates, StringComparer.OrdinalIgnoreCase);
                for (int i = secStart + 1; i < secEnd; i++)
                {
                    var trimmed = lines[i].Trim();
                    if (trimmed.Length == 0 || trimmed.StartsWith('#') || trimmed.StartsWith(';'))
                        continue;
                    var eq = trimmed.IndexOf('=');
                    if (eq <= 0)
                        continue;
                    var key = trimmed[..eq].Trim();
                    if (pending.TryGetValue(key, out var newVal))
                    {
                        lines[i] = $"{key} = {newVal}";
                        pending.Remove(key);
                    }
                }

                if (pending.Count > 0)
                {
                    int insertAt = secEnd;
                    while (insertAt > secStart + 1 && string.IsNullOrWhiteSpace(lines[insertAt - 1]))
                        insertAt--;
                    foreach (var kv in pending)
                    {
                        lines.Insert(insertAt, $"{kv.Key} = {kv.Value}");
                        insertAt++;
                    }
                }
            }

            var dir = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(dir))
                Directory.CreateDirectory(dir);
            File.WriteAllLines(path, lines, new UTF8Encoding(false));
            return true;
        }
        catch
        {
            return false;
        }
    }
}
