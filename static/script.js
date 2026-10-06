// =========================================
// GET TEXTAREAS
// =========================================

const assignment1 =
    document.querySelector('textarea[name="assignment1"]');

const assignment2 =
    document.querySelector('textarea[name="assignment2"]');


// =========================================
// UPDATE WORD AND CHARACTER COUNT
// =========================================

function updateCount(
    textarea,
    wordCountElement,
    characterCountElement
) {

    const text = textarea.value;


    // Count characters

    const characters = text.length;


    // Count words

    const words =
        text.trim() === ""
            ? 0
            : text.trim().split(/\s+/).length;


    // Display counts

    wordCountElement.textContent =
        `Words: ${words}`;

    characterCountElement.textContent =
        `Characters: ${characters}`;
}


// =========================================
// ASSIGNMENT 1 COUNTERS
// =========================================

const assignment1WordCount =
    document.createElement("span");

const assignment1CharacterCount =
    document.createElement("span");


assignment1WordCount.className = "count";

assignment1CharacterCount.className = "count";


assignment1.parentElement.appendChild(
    assignment1WordCount
);

assignment1.parentElement.appendChild(
    assignment1CharacterCount
);


// =========================================
// ASSIGNMENT 2 COUNTERS
// =========================================

const assignment2WordCount =
    document.createElement("span");

const assignment2CharacterCount =
    document.createElement("span");


assignment2WordCount.className = "count";

assignment2CharacterCount.className = "count";


assignment2.parentElement.appendChild(
    assignment2WordCount
);

assignment2.parentElement.appendChild(
    assignment2CharacterCount
);


// =========================================
// ASSIGNMENT 1 LIVE COUNT
// =========================================

assignment1.addEventListener(
    "input",
    function () {

        updateCount(
            assignment1,
            assignment1WordCount,
            assignment1CharacterCount
        );

    }
);


// =========================================
// ASSIGNMENT 2 LIVE COUNT
// =========================================

assignment2.addEventListener(
    "input",
    function () {

        updateCount(
            assignment2,
            assignment2WordCount,
            assignment2CharacterCount
        );

    }
);


// =========================================
// INITIAL COUNTS
// =========================================

updateCount(
    assignment1,
    assignment1WordCount,
    assignment1CharacterCount
);


updateCount(
    assignment2,
    assignment2WordCount,
    assignment2CharacterCount
);


// =========================================
// FILE UPLOAD
// =========================================

const file1 =
    document.getElementById("file1");

const file2 =
    document.getElementById("file2");


const file1Name =
    document.getElementById("file1-name");

const file2Name =
    document.getElementById("file2-name");


// =========================================
// ASSIGNMENT 1 FILE
// =========================================

file1.addEventListener(
    "change",
    function () {

        if (file1.files.length > 0) {

            file1Name.textContent =
                "✓ " +
                file1.files[0].name +
                " selected";

        } else {

            file1Name.textContent =
                "No file selected";

        }

    }
);


// =========================================
// ASSIGNMENT 2 FILE
// =========================================

file2.addEventListener(
    "change",
    function () {

        if (file2.files.length > 0) {

            file2Name.textContent =
                "✓ " +
                file2.files[0].name +
                " selected";

        } else {

            file2Name.textContent =
                "No file selected";

        }

    }
);// =========================================
// REPORT SEARCH / FILTER / SORT
// =========================================

const reportSearch =
    document.getElementById("reportSearch");

const similarityFilter =
    document.getElementById("similarityFilter");

const reportSort =
    document.getElementById("reportSort");

const reportsTableBody =
    document.getElementById("reportsTableBody");

const visibleReportCount =
    document.getElementById("visibleReportCount");


function getSimilarityCategory(similarity) {

    if (similarity >= 70) {

        return "high";

    }

    if (similarity >= 40) {

        return "moderate";

    }

    return "low";
}


function updateReports() {

    if (!reportsTableBody) {
        return;
    }


    const rows = Array.from(
        reportsTableBody.querySelectorAll(".report-row")
    );


    const searchText =
        reportSearch
            ? reportSearch.value.toLowerCase().trim()
            : "";


    const filter =
        similarityFilter
            ? similarityFilter.value
            : "all";


    const sort =
        reportSort
            ? reportSort.value
            : "newest";


    // =========================================
    // FILTER
    // =========================================

    rows.forEach(function(row) {

        const reportId =
            row.dataset.id;

        const similarity =
            parseFloat(row.dataset.similarity);


        const category =
            getSimilarityCategory(similarity);


        const matchesSearch =
            reportId
                .toLowerCase()
                .includes(
                    searchText.replace(
                        "report",
                        ""
                    ).trim()
                );


        const matchesFilter =
            filter === "all" ||
            category === filter;


        if (
            matchesSearch &&
            matchesFilter
        ) {

            row.style.display = "";

        } else {

            row.style.display = "none";

        }

    });


    // =========================================
    // SORT
    // =========================================

    rows.sort(function(a, b) {

        const similarityA =
            parseFloat(
                a.dataset.similarity
            );


        const similarityB =
            parseFloat(
                b.dataset.similarity
            );


        const dateA =
            parseInt(
                a.dataset.date
            );


        const dateB =
            parseInt(
                b.dataset.date
            );


        if (sort === "highest") {

            return similarityB - similarityA;

        }


        if (sort === "lowest") {

            return similarityA - similarityB;

        }


        if (sort === "oldest") {

            return dateA - dateB;

        }


        return dateB - dateA;

    });


    rows.forEach(function(row) {

        reportsTableBody.appendChild(row);

    });


    // =========================================
    // UPDATE COUNT
    // =========================================

    const visibleRows =
        rows.filter(function(row) {

            return row.style.display !== "none";

        });


    if (visibleReportCount) {

        visibleReportCount.textContent =
            visibleRows.length;

    }

}


// =========================================
// SEARCH EVENT
// =========================================

if (reportSearch) {

    reportSearch.addEventListener(
        "input",
        updateReports
    );

}


// =========================================
// FILTER EVENT
// =========================================

if (similarityFilter) {

    similarityFilter.addEventListener(
        "change",
        updateReports
    );

}


// =========================================
// SORT EVENT
// =========================================

if (reportSort) {

    reportSort.addEventListener(
        "change",
        updateReports
    );

}


// =========================================
// INITIALIZE
// =========================================

updateReports();