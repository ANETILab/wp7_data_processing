-- pandoc --citeproc --bibliography references.bib -f asciidoc -t latex data_engineering.adoc -o data_engineering.tex --lua-filter=ignore_asciidoc_bibliography.lua
function Para(el)
    local text = pandoc.utils.stringify(el)
    io.stderr:write("PARA: [" .. text .. "]\n")

    if text == "bibliography::[]" then
        io.stderr:write("MATCHED\n")
        return {}
    end
end
