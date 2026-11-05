package eval;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 评测结果落盘（JUnit 场景用），产出的 JSON 形状与
 * {@code assets/eval_baseline.py} 完全一致。
 *
 * <p><b>为什么每个 suite 一个分片</b>：surefire 默认并发跑测试类，
 * 共用一个 results.json 是"读-改-写"，后写的会覆盖先写的，且丢失是静默的。
 * 分片文件几乎不会撞名，汇总交给 {@code eval_baseline.py} 的目录模式。</p>
 *
 * <p><b>为什么不写在 target/ 下</b>：{@code mvn clean} 会删掉它，
 * 多模块构建也会互相覆盖。放在模块根的独立目录（如 {@code eval-results/}），
 * 只把规则文件与 README 进版本库，结果本身 gitignore。</p>
 *
 * <p>用法：</p>
 * <pre>{@code
 * EvalResults.record("PII 脱敏", passed, total, failures);
 * }</pre>
 *
 * @author L
 */
public final class EvalResults {

    /** 结果目录：可用 -Deval.results.dir 覆盖 */
    private static final String DIR = System.getProperty("eval.results.dir", "eval-results");

    private EvalResults() {
    }

    /**
     * 记录一个 suite 的结果。
     *
     * @param suite    评测名（会成为文件名的一部分，只用可移植字符）
     * @param passed   通过数
     * @param total    总数
     * @param failures 失败明细（可为 null）；写进文件是为了让红的时候不用翻完整日志
     */
    public static void record(String suite, int passed, int total, List<String> failures) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("suite", suite);
        // kind 决定基线的严格度：offline 是纯函数、容忍度 0。
        // Python 版 record() 写入同名字段；Java 版原先漏了，靠文件名前缀
        // 兜底才能推出 offline——那是隐式依赖，改文件名就会静默变档。
        payload.put("kind", "offline");
        payload.put("passed", passed);
        payload.put("total", total);
        payload.put("rate", total == 0 ? 0.0 : Math.round(passed * 10000.0 / total) / 10000.0);
        payload.put("failures", failures == null ? List.of() : failures);
        // 必须与 consolidate() 用同一个定位方式：record() 原先直接 Path.of(DIR,...)
        // 按当前工作目录解析，而 surefire 的 cwd 不保证是模块根（多模块构建时可能是父目录）。
        // 两者不一致时，分片写到 A、consolidate 去 B 找，结果"分片存在但汇总为空"，静默丢数据。
        write(locateDir().resolve("offline-" + safe(suite) + ".json"), payload);
    }

    /**
     * 汇总所有分片成一个文件（给不方便用目录模式的调用方）。
     *
     * <p>产出形状：{@code {"suites": {name: <分片对象>}}}。分片原文本身是合法 JSON，
     * 这里用 {@link RawJson} 原样内嵌——若直接 put 字符串，会被序列化成语义上的
     * "转义后的 JSON 文本"，Python 侧读到的是 string 而不是 object，跨语言读取就断了。</p>
     *
     * @return 汇总文件路径
     */
    public static Path consolidate() {
        Path dir = locateDir();
        Map<String, Object> suites = new LinkedHashMap<>();
        try (var stream = Files.list(dir)) {
            for (Path p : stream.filter(f -> f.getFileName().toString().endsWith(".json")).sorted().toList()) {
                String name = p.getFileName().toString();
                if (name.equals("results.json")) {
                    continue;
                }
                String text = Files.readString(p, StandardCharsets.UTF_8);
                String suite = extractSuite(text);
                if (suite != null) {
                    suites.put(suite, new RawJson(text));
                }
            }
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        Path target = dir.resolve("results.json");
        write(target, Map.of("suites", suites));
        return target;
    }

    /** 预序列化好的 JSON 片段：序列化时原样输出、不加引号（内嵌分片用） */
    private record RawJson(String json) {
    }

    /** 从分片里抠出 suite 名（不引 JSON 库，避免测试代码多一个依赖） */
    private static String extractSuite(String json) {
        int i = json.indexOf("\"suite\"");
        if (i < 0) {
            return null;
        }
        int colon = json.indexOf(':', i);
        int q1 = json.indexOf('"', colon + 1);
        int q2 = q1 < 0 ? -1 : json.indexOf('"', q1 + 1);
        return (q1 < 0 || q2 < 0) ? null : json.substring(q1 + 1, q2);
    }

    /**
     * 定位结果目录。
     *
     * <p>不能直接用 {@code Path.of("eval-results")}：surefire 的工作目录
     * 不保证是模块根（多模块构建时可能是父目录），会让结果落到意外位置。
     * 这里从 {@code user.dir} 逐级向上找模块根标记。</p>
     */
    private static Path locateDir() {
        Path base = Path.of(System.getProperty("user.dir")).toAbsolutePath();
        for (Path p = base; p != null; p = p.getParent()) {
            if (Files.isDirectory(p.resolve("src/main/java"))) {
                Path dir = p.resolve(DIR);
                mkdirs(dir);
                return dir;
            }
        }
        Path dir = base.resolve(DIR);
        mkdirs(dir);
        return dir;
    }

    private static void mkdirs(Path dir) {
        try {
            Files.createDirectories(dir);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static String safe(String name) {
        String cleaned = name.replaceAll("[\\\\/:*?\"<>|\\s]+", "_");
        cleaned = cleaned.replaceAll("^_+|_+$", "");
        return cleaned.isEmpty() ? "suite" : cleaned;
    }

    /** 先写临时文件再改名：进程被杀时不会留下半个 JSON 让基线对比读到坏数据 */
    private static void write(Path path, Object payload) {
        try {
            Files.createDirectories(path.getParent());
            Path tmp = path.resolveSibling(path.getFileName() + ".tmp");
            Files.writeString(tmp, toJson(payload), StandardCharsets.UTF_8);
            Files.move(tmp, path, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    /** 极简 JSON 序列化：只覆盖 Map/List/String/Number/Boolean，够用且零依赖 */
    private static String toJson(Object v) {
        StringBuilder sb = new StringBuilder();
        append(sb, v, 0);
        return sb.append('\n').toString();
    }

    private static void append(StringBuilder sb, Object v, int indent) {
        String pad = "  ".repeat(indent);
        String pad2 = "  ".repeat(indent + 1);
        if (v == null) {
            sb.append("null");
        } else if (v instanceof RawJson raw) {
            // 内嵌预序列化好的片段。strip 掉分片文件末尾的换行，否则缩进会乱。
            // 注意不能走 quote()：那是给字符串值用的，会把整段 JSON 转义成一个字符串，
            // Python 侧读到 str 而不是 dict，跨语言读取就断了。
            sb.append(raw.json().strip());
        } else if (v instanceof Map<?, ?> map) {
            if (map.isEmpty()) {
                sb.append("{}");
                return;
            }
            sb.append("{\n");
            var it = map.entrySet().iterator();
            while (it.hasNext()) {
                var e = it.next();
                sb.append(pad2).append(quote(String.valueOf(e.getKey()))).append(": ");
                append(sb, e.getValue(), indent + 1);
                sb.append(it.hasNext() ? ",\n" : "\n");
            }
            sb.append(pad).append('}');
        } else if (v instanceof List<?> list) {
            if (list.isEmpty()) {
                sb.append("[]");
                return;
            }
            sb.append("[\n");
            for (int i = 0; i < list.size(); i++) {
                sb.append(pad2);
                append(sb, list.get(i), indent + 1);
                sb.append(i == list.size() - 1 ? "\n" : ",\n");
            }
            sb.append(pad).append(']');
        } else if (v instanceof Number || v instanceof Boolean) {
            sb.append(v);
        } else {
            sb.append(quote(String.valueOf(v)));
        }
    }

    private static String quote(String s) {
        StringBuilder sb = new StringBuilder(s.length() + 2).append('"');
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
                }
            }
        }
        return sb.append('"').toString();
    }

    /** 便捷：把失败明细建成可变列表 */
    public static List<String> failures() {
        return new ArrayList<>();
    }
}
