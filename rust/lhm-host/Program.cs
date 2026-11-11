using System;
using System.Globalization;
using System.IO;
using System.Text;
using LibreHardwareMonitor.Hardware;

// Отвечает на строки из stdin: «u» — опросить датчики и вывести JSON-массив одной строкой, «q» — выход.
static class Program
{
    static string Esc(string s)
    {
        var sb = new StringBuilder(s.Length + 2);
        sb.Append('"');
        foreach (var c in s)
        {
            switch (c)
            {
                case '"': sb.Append("\\\""); break;
                case '\\': sb.Append("\\\\"); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                default:
                    if (c < 32) sb.AppendFormat("\\u{0:x4}", (int)c); else sb.Append(c);
                    break;
            }
        }
        sb.Append('"');
        return sb.ToString();
    }

    static void Dump(IHardware top, IHardware hw, StringBuilder sb, ref bool first)
    {
        hw.Update();
        foreach (var s in hw.Sensors)
        {
            if (!first) sb.Append(',');
            first = false;
            var v = s.Value.HasValue && !float.IsNaN(s.Value.Value) && !float.IsInfinity(s.Value.Value)
                ? s.Value.Value.ToString("R", CultureInfo.InvariantCulture) : "null";
            sb.Append("{\"i\":").Append(Esc(s.Identifier.ToString()))
              .Append(",\"h\":").Append(Esc(hw.Name))
              .Append(",\"t\":").Append(Esc(top.HardwareType.ToString()))
              .Append(",\"k\":").Append(Esc(s.SensorType.ToString()))
              .Append(",\"n\":").Append(Esc(s.Name))
              .Append(",\"v\":").Append(v).Append('}');
        }
        foreach (var sub in hw.SubHardware) Dump(top, sub, sb, ref first);
    }

    static int Main()
    {
        var c = new Computer
        {
            IsCpuEnabled = true, IsGpuEnabled = true, IsMemoryEnabled = true,
            IsMotherboardEnabled = true, IsStorageEnabled = true, IsControllerEnabled = true,
        };
        c.Open();
        var stdout = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true };
        var stdin = new StreamReader(Console.OpenStandardInput(), Encoding.UTF8);
        string line;
        while ((line = stdin.ReadLine()) != null)
        {
            line = line.Trim();
            if (line == "q") break;
            if (line != "u") continue;
            var sb = new StringBuilder(64 * 1024);
            sb.Append('[');
            bool first = true;
            foreach (var hw in c.Hardware)
            {
                try { Dump(hw, hw, sb, ref first); } catch (Exception) { /* одно устройство не должно ронять опрос */ }
            }
            sb.Append(']');
            stdout.WriteLine(sb.ToString());
        }
        c.Close();
        return 0;
    }
}
