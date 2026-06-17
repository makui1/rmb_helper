package com.rmb.docx2pdf;

import com.aspose.words.Document;
import com.aspose.words.SaveFormat;

import java.io.PrintStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * 命令行用法：
 *   docx2pdf.exe <输出目录> <文件1.docx> [文件2.docx ...]
 *
 * 每行输出：
 *   OK <输出PDF绝对路径>       — 转换成功
 *   ERR <输入路径>: <错误信息> — 转换失败
 *   DONE <成功数>/<总数>       — 最后一行汇总
 *
 * 退出码：
 *   0 — 全部成功
 *   1 — 有文件转换失败
 *   2 — 参数错误 / 输出目录无法创建
 */
public class Main {

    public static void main(String[] args) {
        try {
            // 强制 UTF-8 输出，避免中文路径乱码
            System.setOut(new PrintStream(System.out, true, "UTF-8"));
            System.setErr(new PrintStream(System.err, true, "UTF-8"));
        } catch (Exception ignored) {}

        if (args.length < 2) {
            System.err.println("用法: docx2pdf <输出目录> <文件1.docx> [文件2.docx ...]");
            System.exit(2);
        }

        // 创建输出目录
        Path outDir = Paths.get(args[0]);
        try {
            Files.createDirectories(outDir);
        } catch (Exception e) {
            System.err.println("无法创建输出目录 " + outDir + ": " + e.getMessage());
            System.exit(2);
        }

        int total = args.length - 1;
        int success = 0;

        for (int i = 1; i <= total; i++) {
            String inputPath = args[i];
            Path inPath = Paths.get(inputPath);
            String baseName = inPath.getFileName().toString();
            // 将 .docx 扩展名替换为 .pdf（不区分大小写）
            String pdfName = baseName.replaceAll("(?i)\\.docx$", ".pdf");
            Path outPath = outDir.resolve(pdfName);

            try {
                Document doc = new Document(inputPath);
                doc.save(outPath.toString(), SaveFormat.PDF);
                System.out.println("OK " + outPath.toAbsolutePath());
                success++;
            } catch (Exception e) {
                System.out.println("ERR " + inputPath + ": " + e.getMessage());
            }
        }

        System.out.println("DONE " + success + "/" + total);
        System.exit(success == total ? 0 : 1);
    }
}
